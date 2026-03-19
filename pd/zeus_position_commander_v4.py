"""
╔══════════════════════════════════════════════════════════════════════╗
║              ZEUS POSITION COMMANDER  v4                           ║
║                                                                      ║
║  목적: 최적 포지션 사이징 + ATR 기반 SL/TP + 포트폴리오 리스크 분석  ║
║                                                                      ║
║  전략:                                                               ║
║    [1] Risk Parity  — 공분산 기반 Equal Risk Contribution           ║
║    [2] Half-Kelly   — Sharpe 비율 기반 Kelly Criterion              ║
║    [3] Equal Weight — 단순 균등 배분 (벤치마크)                      ║
║                                                                      ║
║  수정 이력:                                                           ║
║    v4: Kelly 수식 수정(mean/var→Sharpe 기반), Risk Parity 공분산     ║
║        행렬 도입, clip-normalize 반복, VaR/CVaR 추가,               ║
║        단일종목 MultiIndex 버그 수정, SL 음수 방지,                  ║
║        연변동성/기대수익/상관계수 테이블 추가                         ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import yfinance as yf
import pandas as pd
import numpy as np
import sys
import os
import subprocess
from datetime import datetime
from typing import Dict, Tuple, List

# ══════════════════════════════════════════════════════════════════════
#  설정 (모두 여기서만 수정)
# ══════════════════════════════════════════════════════════════════════
MAX_WEIGHT    : float = 0.30   # 종목당 최대 비중 (30%)
MIN_WEIGHT    : float = 0.02   # 종목당 최소 비중 (2% 미만 제외)
KELLY_FRAC    : float = 0.50   # Half-Kelly (0.5 = 보수적, 1.0 = 풀켈리)
RISK_FREE     : float = 0.045  # 무위험 수익률 (10Y Treasury ~4.5%)
ATR_PERIOD    : int   = 14     # ATR 기간 (일)
SL_MULT       : float = 2.0    # 손절: 현재가 - SL_MULT × ATR
TP_MULT       : float = 3.0    # 익절: 현재가 + TP_MULT × ATR
SL_MIN_PCT    : float = 0.03   # 손절 최소 하락폭 (3%) — 음수 손절가 방지
VAR_CONF      : float = 0.95   # VaR 신뢰수준 (95%)
DATA_PERIOD   : str   = "3y"   # 데이터 기간 (3년 — 1년은 과적합)
CLIP_ITER     : int   = 10     # clip-normalize 반복 횟수
OUTPUT_FILE   : str   = "commander_report.html"


# ══════════════════════════════════════════════════════════════════════
#  1. 데이터 수집
# ══════════════════════════════════════════════════════════════════════
def fetch_data(tickers: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    OHLCV 수집. yfinance MultiIndex 완전 호환.
    Returns: (close_df, high_df, low_df) — 각각 [날짜 × 종목] DataFrame
    """
    print(f"  📡 데이터 수집 중... ({len(tickers)}개 종목, {DATA_PERIOD})")
    raw = yf.download(tickers, period=DATA_PERIOD, progress=False, auto_adjust=True)

    # ── MultiIndex 정규화 (yfinance 버전 무관) ─────────────────────
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"]
        high  = raw["High"]
        low   = raw["Low"]
    else:
        # 단일 종목 → 컬럼이 flat
        close = raw[["Close"]].rename(columns={"Close": tickers[0]})
        high  = raw[["High"]].rename(columns={"High":  tickers[0]})
        low   = raw[["Low"]].rename(columns={"Low":   tickers[0]})

    # 수집 실패 종목 체크
    missing = [t for t in tickers if t not in close.columns or close[t].dropna().empty]
    if missing:
        print(f"  ⚠️  데이터 없는 종목 제외: {missing}")
        for m in missing:
            tickers.remove(m)

    close = close[tickers].dropna(how="all")
    high  = high[tickers].dropna(how="all")
    low   = low[tickers].dropna(how="all")

    print(f"  ✅ 수집 완료: {len(close)}거래일 × {len(tickers)}종목")
    return close, high, low


# ══════════════════════════════════════════════════════════════════════
#  2. ATR 계산
# ══════════════════════════════════════════════════════════════════════
def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series) -> float:
    """Wilder ATR (14일). True Range = max(H-L, |H-C_prev|, |L-C_prev|)"""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(span=ATR_PERIOD, adjust=False).mean()  # Wilder = EWM alpha=1/14
    val = atr.iloc[-1]
    return float(val) if np.isfinite(val) else float((high - low).mean())


# ══════════════════════════════════════════════════════════════════════
#  3. 포지션 사이징 전략
# ══════════════════════════════════════════════════════════════════════

def _clip_normalize(w: pd.Series, max_w: float, min_w: float, n_iter: int) -> pd.Series:
    """
    clip → normalize 반복.
    단순 1회 clip 후 재정규화하면 일부 종목이 max_w 초과 가능.
    반복하면 모든 종목이 [min_w, max_w] 범위 내로 수렴.
    """
    for _ in range(n_iter):
        w = w.clip(lower=0)
        total = w.sum()
        if total <= 0:
            return pd.Series(1.0 / len(w), index=w.index)
        w = w / total
        w = w.clip(upper=max_w)
        # min_w 미만 종목 제거 후 재정규화
        w[w < min_w] = 0.0
    total = w.sum()
    return w / total if total > 0 else pd.Series(1.0 / (w > 0).sum(), index=w.index)


def strategy_equal_weight(close: pd.DataFrame) -> Tuple[pd.Series, pd.DataFrame]:
    """균등 배분 — 기준선(벤치마크)"""
    n = len(close.columns)
    w = pd.Series(1.0 / n, index=close.columns)
    w = _clip_normalize(w, MAX_WEIGHT, MIN_WEIGHT, CLIP_ITER)
    stats = _compute_stats(close)
    return w, stats


def strategy_risk_parity(close: pd.DataFrame) -> Tuple[pd.Series, pd.DataFrame]:
    """
    공분산 기반 Equal Risk Contribution (True Risk Parity).
    단순 역변동성이 아닌, 공분산 행렬을 써서 종목간 상관관계까지 반영.

    ERC 수치 해법 (Newton iteration):
      각 종목 리스크 기여도 = w_i * (Σw)_i / sqrt(w'Σw) 가 모두 같도록.
    """
    returns = close.pct_change().dropna()
    cov     = returns.cov() * 252          # 연환산 공분산
    n       = len(close.columns)

    # ── Newton-Raphson으로 ERC 가중치 계산 ──────────────────────────
    w = np.ones(n) / n                     # 초기값: 균등
    for _ in range(300):
        sigma   = float(np.sqrt(w @ cov.values @ w))
        if sigma < 1e-10:
            break
        grad    = (cov.values @ w) / sigma  # 종목별 한계 리스크 기여
        risk_c  = w * grad                  # 종목별 리스크 기여
        target  = sigma / n                 # 목표 리스크 기여 (균등)
        w       = w * (target / (risk_c + 1e-10))
        w       = np.maximum(w, 0)
        w       = w / w.sum()

    weights = pd.Series(w, index=close.columns)
    weights = _clip_normalize(weights, MAX_WEIGHT, MIN_WEIGHT, CLIP_ITER)
    stats   = _compute_stats(close)
    return weights, stats


def strategy_half_kelly(close: pd.DataFrame) -> Tuple[pd.Series, pd.DataFrame]:
    """
    Sharpe 기반 Fractional Kelly.

    Kelly fraction = (mu - rf) / sigma^2
      mu    = 연간 기대수익률
      rf    = 무위험 수익률
      sigma = 연간 변동성

    주의:
      - 음수 초과수익 종목 → weight = 0 (투자 안 함)
      - Half-Kelly(×0.5) 적용으로 과도한 집중 방지
      - clip-normalize로 최대 비중 제한
    """
    returns = close.pct_change().dropna()
    mu      = returns.mean() * 252
    sigma   = returns.std()  * np.sqrt(252)
    sigma2  = sigma ** 2

    excess  = mu - RISK_FREE
    kelly_w = excess / sigma2.replace(0, np.nan)  # 0 나누기 방지
    kelly_w = kelly_w.fillna(0).clip(lower=0) * KELLY_FRAC

    # 모든 종목이 음수수익이면 전액 현금 보유
    if kelly_w.sum() <= 0:
        print("  ⚠️  모든 종목 기대 초과수익 ≤ 0 → 전략 결과 없음 (Equal Weight 대체)")
        return strategy_equal_weight(close)

    weights = _clip_normalize(kelly_w, MAX_WEIGHT, MIN_WEIGHT, CLIP_ITER)
    stats   = _compute_stats(close)
    return weights, stats


# ══════════════════════════════════════════════════════════════════════
#  4. 통계 계산
# ══════════════════════════════════════════════════════════════════════
def _compute_stats(close: pd.DataFrame) -> pd.DataFrame:
    """종목별 연환산 수익률, 변동성, Sharpe, 최대낙폭"""
    r = close.pct_change().dropna()
    mu    = r.mean() * 252
    sigma = r.std()  * np.sqrt(252)
    sharpe = (mu - RISK_FREE) / sigma.replace(0, np.nan)

    mdd_list = []
    for col in close.columns:
        cumret  = (1 + r[col]).cumprod()
        rolling = cumret.cummax()
        dd      = (cumret - rolling) / rolling
        mdd_list.append(dd.min())
    mdd = pd.Series(mdd_list, index=close.columns)

    return pd.DataFrame({
        "연수익률(%)": (mu * 100).round(1),
        "연변동성(%)": (sigma * 100).round(1),
        "Sharpe":      sharpe.round(2),
        "MDD(%)":      (mdd * 100).round(1),
    })


def portfolio_risk(weights: pd.Series, close: pd.DataFrame) -> Dict:
    """
    포트폴리오 수준 리스크:
      - 포트폴리오 변동성 (공분산 기반)
      - 95% VaR (Historical Simulation)
      - 95% CVaR (Expected Shortfall)
      - 분산 효과 = 1 - port_vol / weighted_avg_vol
    """
    r   = close[weights.index].pct_change().dropna()
    w   = weights.values
    cov = r.cov().values * 252
    
    port_vol    = float(np.sqrt(w @ cov @ w)) * 100
    indiv_vols  = np.sqrt(np.diag(cov)) * 100
    wavg_vol    = float(w @ indiv_vols)
    div_benefit = max(0.0, (wavg_vol - port_vol) / max(wavg_vol, 0.01) * 100)

    # Daily P&L series
    port_daily  = (r * weights).sum(axis=1)
    var_95      = float(np.percentile(port_daily, (1 - VAR_CONF) * 100)) * 100
    cvar_95     = float(port_daily[port_daily <= np.percentile(port_daily, (1-VAR_CONF)*100)].mean()) * 100

    return {
        "port_vol":      round(port_vol, 2),
        "wavg_vol":      round(wavg_vol, 2),
        "div_benefit":   round(div_benefit, 1),
        "var_95":        round(var_95, 2),     # 음수: 하루 최대 손실 %
        "cvar_95":       round(cvar_95, 2),    # 음수
    }


# ══════════════════════════════════════════════════════════════════════
#  5. HTML 리포트
# ══════════════════════════════════════════════════════════════════════
def generate_html(
    tickers:       List[str],
    weights:       pd.Series,
    close:         pd.DataFrame,
    high:          pd.DataFrame,
    low:           pd.DataFrame,
    total_capital: float,
    strategy_name: str,
    stats:         pd.DataFrame,
    port_risk:     Dict,
    corr_matrix:   pd.DataFrame,
) -> str:
    latest = close.iloc[-1]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── 종목별 행 생성 ───────────────────────────────────────────────
    rows_html = ""
    total_allocated = 0.0

    for tk in tickers:
        w = float(weights.get(tk, 0))
        if w < MIN_WEIGHT:
            continue

        price  = float(latest[tk])
        amount = total_capital * w
        shares = int(amount // price)
        actual = shares * price
        total_allocated += actual

        atr    = calc_atr(high[tk], low[tk], close[tk])
        sl_raw = price - SL_MULT * atr
        # SL 최소 하한: 현재가 × (1 - SL_MIN_PCT) 와 비교해 높은 쪽 사용
        sl_min = price * (1 - SL_MIN_PCT)
        sl     = max(sl_raw, sl_min, 0.01)
        tp     = price + TP_MULT * atr

        sl_pct = (sl / price - 1) * 100
        tp_pct = (tp / price - 1) * 100
        rr     = abs(tp_pct / sl_pct) if sl_pct != 0 else 0  # Risk:Reward 비율

        s = stats.loc[tk]

        rows_html += f"""
        <tr>
          <td class="ticker">{tk}</td>
          <td>${price:,.2f}</td>
          <td class="green bold">{shares}주</td>
          <td><span class="purple bold">{w*100:.1f}%</span>
              <br><small class="dim">${actual:,.0f}</small></td>
          <td class="dim">{s['연수익률(%)']:+.1f}%</td>
          <td class="dim">{s['연변동성(%)']:.1f}%</td>
          <td class="{'green' if s['Sharpe']>0 else 'red'} bold">{s['Sharpe']:.2f}</td>
          <td class="red bold">${sl:,.2f}<br><small class="red">{sl_pct:.1f}%</small></td>
          <td class="green bold">${tp:,.2f}<br><small class="green">+{tp_pct:.1f}%</small></td>
          <td class="dim">{rr:.1f}:1</td>
        </tr>"""

    cash_left = total_capital - total_allocated

    # ── 상관관계 테이블 ──────────────────────────────────────────────
    corr_header = "".join(f"<th>{t}</th>" for t in corr_matrix.columns)
    corr_rows   = ""
    for idx, row in corr_matrix.iterrows():
        cells = ""
        for col, val in row.items():
            if idx == col:
                cells += f'<td class="dim">—</td>'
            else:
                color = "red" if val > 0.7 else "yellow" if val > 0.4 else "green"
                cells += f'<td class="{color}">{val:.2f}</td>'
        corr_rows += f"<tr><td class='ticker'>{idx}</td>{cells}</tr>"

    # ── 포트폴리오 리스크 박스 ───────────────────────────────────────
    var_color  = "red" if port_risk["var_95"]  < -3 else "yellow" if port_risk["var_95"]  < -1.5 else "green"
    cvar_color = "red" if port_risk["cvar_95"] < -4 else "yellow" if port_risk["cvar_95"] < -2.0 else "green"

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>ZEUS Position Commander v4</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; padding: 32px; }}
  .wrap {{ max-width: 1200px; margin: 0 auto; }}
  h1 {{ color: #58a6ff; text-align: center; font-size: 26px; margin-bottom: 4px; }}
  .sub {{ text-align: center; color: #8b949e; font-size: 13px; margin-bottom: 28px; }}
  .cards {{ display: flex; gap: 16px; margin-bottom: 28px; flex-wrap: wrap; }}
  .card {{ flex: 1; min-width: 140px; background: #161b22; border: 1px solid #30363d;
           border-radius: 10px; padding: 18px; text-align: center; }}
  .card .label {{ font-size: 11px; color: #8b949e; text-transform: uppercase; margin-bottom: 8px; }}
  .card .val {{ font-size: 22px; font-weight: 700; }}
  h2 {{ color: #58a6ff; font-size: 16px; margin: 28px 0 12px; border-bottom: 1px solid #30363d; padding-bottom: 6px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; margin-bottom: 12px; }}
  th {{ color: #8b949e; font-size: 11px; text-transform: uppercase; padding: 8px 10px;
        text-align: right; border-bottom: 2px solid #30363d; }}
  th:first-child {{ text-align: left; }}
  td {{ padding: 10px 10px; text-align: right; border-bottom: 1px solid #21262d; vertical-align: middle; }}
  td:first-child {{ text-align: left; }}
  tr:hover {{ background: #1c2128; }}
  .ticker {{ font-weight: 700; color: #58a6ff; font-size: 16px; }}
  .bold {{ font-weight: 700; }}
  .green {{ color: #3fb950; }} .red {{ color: #f85149; }}
  .yellow {{ color: #d29922; }} .purple {{ color: #d2a8ff; }}
  .dim {{ color: #8b949e; font-size: 12px; }}
  small {{ font-size: 11px; }}
  .risk-grid {{ display: grid; grid-template-columns: repeat(5,1fr); gap: 12px; margin-bottom: 28px; }}
  .risk-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px;
               padding: 14px; text-align: center; }}
  .risk-card .rl {{ font-size: 11px; color: #8b949e; margin-bottom: 6px; }}
  .risk-card .rv {{ font-size: 18px; font-weight: 700; }}
  .note {{ font-size: 12px; color: #8b949e; margin-top: 8px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>🚀 ZEUS Position Commander v4</h1>
  <div class="sub">{now_str} | 전략: {strategy_name} | 기간: {DATA_PERIOD} | Half-Kelly: {KELLY_FRAC}</div>

  <!-- 요약 카드 -->
  <div class="cards">
    <div class="card"><div class="label">총 예산</div><div class="val">${total_capital:,.0f}</div></div>
    <div class="card"><div class="label">실배분</div><div class="val green">${total_allocated:,.0f}</div></div>
    <div class="card"><div class="label">잔여 현금</div><div class="val">${cash_left:,.0f}</div></div>
    <div class="card"><div class="label">투자 종목수</div><div class="val">{(weights >= MIN_WEIGHT).sum()}개</div></div>
    <div class="card"><div class="label">포트폴리오 변동성</div><div class="val yellow">{port_risk['port_vol']:.1f}%/년</div></div>
  </div>

  <!-- 포트폴리오 리스크 -->
  <h2>📊 포트폴리오 리스크 분석</h2>
  <div class="risk-grid">
    <div class="risk-card"><div class="rl">포트폴리오 변동성</div><div class="rv yellow">{port_risk['port_vol']:.1f}%</div></div>
    <div class="risk-card"><div class="rl">가중평균 개별변동성</div><div class="rv">{port_risk['wavg_vol']:.1f}%</div></div>
    <div class="risk-card"><div class="rl">분산 효과</div><div class="rv green">{port_risk['div_benefit']:.1f}%p</div></div>
    <div class="risk-card"><div class="rl">1일 VaR (95%)</div><div class="rv {var_color}">{port_risk['var_95']:.2f}%</div></div>
    <div class="risk-card"><div class="rl">1일 CVaR (95%)</div><div class="rv {cvar_color}">{port_risk['cvar_95']:.2f}%</div></div>
  </div>
  <p class="note">VaR: 95% 확률로 하루 손실이 이 값 이하. CVaR: VaR 초과 손실의 평균(꼬리 리스크).</p>

  <!-- 포지션 테이블 -->
  <h2>💼 포지션 사이징</h2>
  <table>
    <thead>
      <tr>
        <th>종목</th><th>현재가</th><th>주문수량</th><th>비중(금액)</th>
        <th>연수익률</th><th>연변동성</th><th>Sharpe</th>
        <th>🛑 손절가</th><th>🎯 익절가</th><th>손익비</th>
      </tr>
    </thead>
    <tbody>{rows_html}</tbody>
  </table>
  <p class="note">손절가 = 현재가 − {SL_MULT}×ATR{ATR_PERIOD}일 (최소 하락폭 {SL_MIN_PCT*100:.0f}% 보장) | 익절가 = 현재가 + {TP_MULT}×ATR | ATR = Wilder EWM</p>

  <!-- 상관관계 -->
  <h2>🔗 종목간 상관관계 (3년 일간수익률)</h2>
  <table>
    <thead><tr><th>종목</th>{corr_header}</tr></thead>
    <tbody>{corr_rows}</tbody>
  </table>
  <p class="note">🟢 r&lt;0.4 분산 충분 | 🟡 0.4≤r&lt;0.7 주의 | 🔴 r≥0.7 과집중 — 실질 분산 효과 없음</p>

</div>
</body>
</html>"""

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), OUTPUT_FILE)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


# ══════════════════════════════════════════════════════════════════════
#  6. 메인
# ══════════════════════════════════════════════════════════════════════
def main() -> None:
    print("\n" + "═"*60)
    print("  🚀 ZEUS Position Commander v4")
    print("═"*60)

    # ── 입력 ────────────────────────────────────────────────────────
    raw = input("  ▶ 티커 입력 (예: NVDA, IONQ, RTX)\n  > ").strip()
    if not raw:
        sys.exit()
    tickers: List[str] = [t.strip().upper() for t in raw.split(",") if t.strip()]

    raw_cap = input("  ▶ 총 투자 금액 USD (예: 10000)\n  > ").strip()
    total_capital = float(raw_cap) if raw_cap else 10_000.0

    print("\n  전략 선택:")
    print("    [1] Risk Parity  — 공분산 기반 균등 리스크 기여 (추천)")
    print("    [2] Half-Kelly   — Sharpe 기반 켈리 공식 (공격적)")
    print("    [3] Equal Weight — 단순 균등 배분 (기준선)")
    choice = input("  > ").strip()

    # ── 데이터 수집 ──────────────────────────────────────────────────
    close, high, low = fetch_data(tickers)
    tickers = list(close.columns)  # 수집 실패 종목 제외 후 갱신

    if len(tickers) == 0:
        print("  ❌ 유효한 종목이 없습니다.")
        sys.exit()

    # ── 전략 계산 ────────────────────────────────────────────────────
    print("\n  ⚙️  포지션 계산 중...")
    if choice == "2":
        weights, stats = strategy_half_kelly(close)
        strategy_name = f"Half-Kelly (fraction={KELLY_FRAC}, rf={RISK_FREE*100:.1f}%)"
    elif choice == "3":
        weights, stats = strategy_equal_weight(close)
        strategy_name = "Equal Weight (균등배분)"
    else:
        weights, stats = strategy_risk_parity(close)
        strategy_name = "Risk Parity (ERC, 공분산 기반)"

    # ── 포트폴리오 리스크 ────────────────────────────────────────────
    active = weights[weights >= MIN_WEIGHT].index.tolist()
    port_risk = portfolio_risk(weights[active], close[active])

    # ── 상관관계 행렬 ────────────────────────────────────────────────
    returns = close[active].pct_change().dropna()
    corr    = returns.corr().round(2)

    # ── 출력 요약 ────────────────────────────────────────────────────
    print(f"\n  {'종목':<8} {'비중':>7} {'연수익':>8} {'연변동':>8} {'Sharpe':>7} {'MDD':>8}")
    print(f"  {'─'*50}")
    for tk in active:
        w = weights[tk]
        s = stats.loc[tk]
        print(f"  {tk:<8} {w*100:>6.1f}%  {s['연수익률(%)']:>+7.1f}%  {s['연변동성(%)']:>7.1f}%  {s['Sharpe']:>6.2f}  {s['MDD(%)']:>7.1f}%")

    print(f"\n  포트폴리오 변동성: {port_risk['port_vol']:.1f}% | 분산효과: +{port_risk['div_benefit']:.1f}%p")
    print(f"  1일 VaR(95%): {port_risk['var_95']:.2f}% | CVaR(95%): {port_risk['cvar_95']:.2f}%")

    # ── 리포트 생성 ──────────────────────────────────────────────────
    out_path = generate_html(
        tickers=active,
        weights=weights,
        close=close,
        high=high,
        low=low,
        total_capital=total_capital,
        strategy_name=strategy_name,
        stats=stats,
        port_risk=port_risk,
        corr_matrix=corr,
    )
    print(f"\n  💾 리포트 저장: {out_path}")

    # ── 브라우저 열기 ────────────────────────────────────────────────
    try:
        if sys.platform == "win32":
            subprocess.Popen(f'start "" "{out_path}"', shell=True)
        else:
            subprocess.Popen(["xdg-open", out_path])
        print("  🌐 브라우저 열기 시도...")
    except Exception:
        print(f"  📂 브라우저에서 직접 열기: {out_path}")

    print("═"*60)


if __name__ == "__main__":
    main()
