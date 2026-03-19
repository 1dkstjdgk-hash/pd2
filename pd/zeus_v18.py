"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                ZEUS ULTIMATE V18 — Hedge Fund Alpha Edition                  ║
║                                                                              ║
║  V17 → V18 핵심 추가 (헤지펀드 기법 흡수):                                  ║
║                                                                              ║
║  [NEW 1] 📐 GARCH 동적 Kelly — Bridgewater 스타일 포지션 사이징             ║
║           GARCH(1,1) 변동성 예측 → 미래 변동성 높으면 Kelly 자동 축소       ║
║           변동성 국면(Low/Normal/High/Extreme) 분류                          ║
║           Risk Parity 보정: 목표 변동성(15%) 기준 포지션 역산                ║
║           VIX 레짐 × 종목 변동성 교차 패널티 적용                           ║
║                                                                              ║
║  [NEW 2] 🧠 MetaLearner 앙상블 — Citadel ML 팀 스타일                       ║
║           1단계: GBM·RF·MLP·XGB 각자 예측 확률 생성                        ║
║           2단계: MetaLearner(GBM)가 시장 국면 피처 + 각 모델 예측을 받아   ║
║                  "이 국면엔 어떤 모델을 얼마나 믿을지" 동적으로 결정        ║
║           국면 피처: VIX 레짐, 변동성, ADX, 추세 강도, BB 수축 여부        ║
║           단순 정확도 가중평균 → 국면 인식 메타 앙상블로 교체               ║
║                                                                              ║
║  V17 유지 기능:                                                               ║
║  [CORE] 🎛️  3-Mode 자동 전환 / ⚡ BounceEngine / 🐻 ShortEngine            ║
║  [    ] 📐 Beta Scaler / 📊 Backtester / 📝 SignalLogger                    ║
║  [    ] Circuit Breaker / VPA / 섹터RS / MTF / 매물대                       ║
║                                                                              ║
║  사용법:                                                                     ║
║    python zeus_v18.py              → 일반 분석                               ║
║    python zeus_v18.py --backtest   → 백테스트 후 분석                        ║
║    python zeus_v18.py --review     → 과거 신호 결과 업데이트                 ║
║    python zeus_v18.py --stats      → 누적 승률 통계                          ║
║                                                                              ║
║  필요 패키지:                                                                 ║
║    pip install yfinance pandas numpy scikit-learn xgboost                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import warnings
warnings.filterwarnings('ignore')
import os, random, sys, csv, json
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

# torch 없이 sklearn MLP 회귀로 Engine B 동작
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.metrics import accuracy_score
from sklearn.pipeline import Pipeline
from sklearn.model_selection import TimeSeriesSplit
from sklearn.inspection import permutation_importance

try:
    from xgboost import XGBClassifier
    XGBOOST_OK = True
except ImportError:
    XGBOOST_OK = False

def set_seed(seed: int = 42):
    random.seed(seed); np.random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)

set_seed(42)
DEVICE = "cpu"  # torch 미사용

# ──────────────────────────────────────────────────────
#  섹터 ETF 매핑
# ──────────────────────────────────────────────────────
SECTOR_MAP: Dict[str, str] = {
    "NVDA":"SOXX","AMD":"SOXX","INTC":"SOXX","AVGO":"SOXX","QCOM":"SOXX",
    "MU":"SOXX","AMAT":"SOXX","LRCX":"SOXX","KLAC":"SOXX","MRVL":"SOXX",
    "AAPL":"XLK","MSFT":"XLK","GOOGL":"XLK","META":"XLK","AMZN":"XLY",
    "TSLA":"XLY","NFLX":"XLY",
    "IONQ":"QTUM","RGTI":"QTUM","QUBT":"QTUM","ARQQ":"QTUM",
    "RKLB":"XAR","ASTS":"XAR",
    "MRNA":"XBI","BNTX":"XBI","NVAX":"XBI","BIIB":"XBI",
    "JNJ":"XLV","PFE":"XLV","ABBV":"XLV","LLY":"XLV","UNH":"XLV",
    "JPM":"XLF","BAC":"XLF","GS":"XLF","MS":"XLF","WFC":"XLF","C":"XLF",
    "XOM":"XLE","CVX":"XLE","COP":"XLE","OXY":"XLE",
    "CAT":"XLI","HON":"XLI","GE":"XLI","RTX":"XLI","LMT":"XAR",
    "NEE":"XLU","D":"XLU","SO":"XLU",
    "AMT":"XLRE","PLD":"XLRE","O":"XLRE",
    "PG":"XLP","KO":"XLP","PEP":"XLP","COST":"XLP",
    "SPY":"SPY","QQQ":"QQQ","IWM":"IWM","SOXX":"SOXX","XLK":"XLK",
}
def get_sector_etf(ticker: str) -> str:
    return SECTOR_MAP.get(ticker.upper(), "QQQ")

# ──────────────────────────────────────────────────────
#  고베타 종목 목록 (손절 배수 확대, 켈리 축소)
# ──────────────────────────────────────────────────────
HIGH_BETA_TICKERS = {
    "IONQ","RGTI","QUBT","ARQQ","RKLB","ASTS","NVAX","MRNA","BNTX",
    "SMCI","MSTR","COIN","HOOD","RIVN","LCID","SOFI","UPST","AFRM",
    "PLTR","SNOW","DDOG","NET","ZS","CRWD","OKTA","DASH","RBLX","U",
    "TSLA","AMD","MU","MRVL",
}
ETF_TICKERS = {
    "SPY","QQQ","IWM","SOXX","XLK","XLY","XLF","XLE","XLI","XLV",
    "XLU","XLRE","XLP","XBI","XAR","QTUM","GLD","SLV","TLT","HYG",
    "ARKK","SOXL","TQQQ","UPRO",
}


# ══════════════════════════════════════════════════════════════
#  [CORE] 장 국면 감지 및 모드 결정
# ══════════════════════════════════════════════════════════════
class MarketRegimeDetector:
    """
    VIX + SPY 모멘텀 + 크레딧 스프레드(HYG) 종합해서
    BULL / SWING / BEAR 모드 자동 결정
    """
    def detect(self, vix: float, spy_ret5: float,
               hyg_ret20: float, dxy: float) -> str:
        """
        Returns: 'bull' | 'swing' | 'bear'
        """
        bear_count = 0
        if vix >= 30:            bear_count += 2   # VIX 공포 = 헤비 시그널
        elif vix >= 23:          bear_count += 1
        if spy_ret5 <= -0.04:    bear_count += 2   # SPY 5일 -4% 이하
        elif spy_ret5 <= -0.02:  bear_count += 1
        if hyg_ret20 <= -0.05:   bear_count += 1   # 하이일드 급락
        if dxy >= 107:           bear_count += 1   # 달러 극강세

        if bear_count >= 4:   return 'bear'
        if bear_count >= 2:   return 'swing'
        return 'bull'


# ══════════════════════════════════════════════════════════════
#  [NEW C] Beta Scaler — 종목 특성별 파라미터 자동 조정
# ══════════════════════════════════════════════════════════════
@dataclass
class BetaProfile:
    ticker_type: str         = "standard"   # "high_beta" | "bigtech" | "etf" | "standard"
    # 손절/익절 ATR 배수 (고베타는 더 넓게)
    stop_atr_mult: float     = 2.0
    target_atr_mult: float   = 4.0
    # 반등 조건 임계값 (고베타는 더 과매도여야 의미있음)
    rsi_oversold: float      = 25.0
    rsi_overbought: float    = 75.0
    # 켈리 비중 스케일러 (고베타는 작게)
    kelly_scale: float       = 1.0
    # Chandelier Exit 배수
    chandelier_mult: float   = 3.0
    # 반등 최소 조건 수 (고베타는 더 많은 확인 필요)
    bounce_min_signals: int  = 2
    # 숏 신뢰도 요구 최소값
    short_min_conf: float    = 60.0


def get_beta_profile(ticker: str) -> BetaProfile:
    t = ticker.upper()
    if t in HIGH_BETA_TICKERS:
        return BetaProfile(
            ticker_type="high_beta",
            stop_atr_mult=2.5,      # 더 넓은 손절 (급변동 견딤)
            target_atr_mult=5.0,    # 더 넓은 익절 (고베타는 크게 움직임)
            rsi_oversold=20.0,      # 더 극단적 과매도여야 반등 의미있음
            rsi_overbought=80.0,
            kelly_scale=0.5,        # 켈리 절반 (고위험)
            chandelier_mult=3.5,
            bounce_min_signals=3,   # 더 많은 확인 필요
            short_min_conf=65.0,
        )
    elif t in ETF_TICKERS:
        return BetaProfile(
            ticker_type="etf",
            stop_atr_mult=1.5,      # 타이트한 손절 (ETF는 덜 급변)
            target_atr_mult=3.0,
            rsi_oversold=30.0,
            rsi_overbought=70.0,
            kelly_scale=1.2,        # ETF는 비중 더 잡아도 됨
            chandelier_mult=2.5,
            bounce_min_signals=2,
            short_min_conf=55.0,
        )
    elif t in {"AAPL","MSFT","GOOGL","META","AMZN","NVDA","AVGO"}:
        return BetaProfile(
            ticker_type="bigtech",
            stop_atr_mult=2.0,
            target_atr_mult=4.0,
            rsi_oversold=28.0,
            rsi_overbought=72.0,
            kelly_scale=0.8,
            chandelier_mult=3.0,
            bounce_min_signals=2,
            short_min_conf=60.0,
        )
    else:
        return BetaProfile()


# ══════════════════════════════════════════════════════════════
#  설정
# ══════════════════════════════════════════════════════════════
@dataclass
class ZeusConfig:
    stop_loss_pct: float               = 0.05
    take_profit_pct: float             = 0.15
    prediction_day_candidates: List[int] = field(default_factory=lambda: [3, 5, 10])
    label_dead_zone: float             = 0.02
    buy_prob_threshold: float          = 0.58
    sell_prob_threshold: float         = 0.42
    cv_folds: int                      = 5
    lookback: int                      = 30
    forecast: int                      = 7
    mc_simulations: int                = 2000
    fusion_agreement_bonus: float      = 10.0
    vix_cb_threshold: float            = 30.0
    dxy_cb_threshold: float            = 105.0
    hyg_drop_threshold: float          = -0.05


# ──────────────────────────────────────────────────────
#  결과 데이터 클래스
# ──────────────────────────────────────────────────────
@dataclass
class EngineAResult:
    prob_up: float=0.; direction: str="HOLD"; cv_accuracy: float=0.; cv_std: float=0.
    kelly_pct: float=0.; optimal_days: int=5; regime: str="normal"
    model_weights: dict=field(default_factory=dict)
    selected_features: list=field(default_factory=list)
    stop_price: float=0.; target_price: float=0.; success: bool=False


# ══════════════════════════════════════════════════════════════
#  [NEW 1] GARCH 동적 Kelly — Bridgewater 스타일 포지션 사이징
# ══════════════════════════════════════════════════════════════
@dataclass
class GARCHResult:
    vol_forecast:    float = 0.      # GARCH 예측 변동성 (일간 표준편차)
    vol_annualized:  float = 0.      # 연환산 변동성 (%)
    vol_regime:      str   = "normal" # "low" | "normal" | "high" | "extreme"
    kelly_raw:       float = 0.      # 기존 Kelly 값
    kelly_garch:     float = 0.      # GARCH 보정 후 Kelly
    kelly_riskparity:float = 0.      # Risk Parity 기반 Kelly
    kelly_final:     float = 0.      # 최종 권장 Kelly (세 값의 보수적 조합)
    vol_percentile:  float = 0.      # 현재 변동성이 과거 대비 몇 %ile
    target_vol:      float = 15.0    # 목표 연환산 변동성 (%)
    scaling_factor:  float = 1.0     # Kelly 조정 배수
    success:         bool  = False


class GARCHKelly:
    """
    GARCH(1,1) 변동성 예측 기반 동적 Kelly 포지션 사이징.

    헤지펀드(Bridgewater Risk Parity)가 쓰는 핵심 아이디어:
    - 변동성이 높을 때 포지션을 줄이고
    - 변동성이 낮을 때 포지션을 늘림
    - 목표 변동성(target_vol=15%)를 기준으로 포지션을 역산

    scipy 없이 순수 numpy로 GARCH(1,1) 파라미터 추정.
    """

    TARGET_VOL = 0.15   # 연환산 15% 목표 변동성

    def _fit_garch(self, rets: np.ndarray) -> Tuple[float, float, float]:
        """
        GARCH(1,1): σ²_t = ω + α·ε²_{t-1} + β·σ²_{t-1}
        MLE 대신 모멘트 매칭(빠른 근사) 사용.
        반환: (omega, alpha, beta)
        """
        r = rets[~np.isnan(rets)]
        if len(r) < 30:
            sig2 = float(np.var(r))
            return sig2 * 0.05, 0.10, 0.85   # 기본값

        var_unc = float(np.var(r))            # 무조건 분산

        # 자기상관으로 alpha+beta 추정
        sq_r = r ** 2
        lag1_corr = float(np.corrcoef(sq_r[:-1], sq_r[1:])[0, 1])
        lag1_corr = max(0.05, min(0.97, lag1_corr))

        # 전형적 범위: alpha ~ 0.05~0.15, beta ~ 0.80~0.92
        alpha = max(0.05, min(0.20, lag1_corr * 0.15))
        beta  = max(0.75, min(0.93, lag1_corr * 0.85))
        if alpha + beta >= 1.0:
            beta = 0.93 - alpha

        omega = var_unc * (1.0 - alpha - beta)
        return float(omega), float(alpha), float(beta)

    def _forecast_vol(self, rets: np.ndarray,
                      omega: float, alpha: float, beta: float,
                      steps: int = 5) -> float:
        """
        현재 분산에서 steps일 앞 분산을 재귀적으로 예측.
        """
        r = rets[~np.isnan(rets)]
        if len(r) < 2:
            return float(np.std(r)) if len(r) else 0.01

        # 현재 분산 (마지막 20일 EWM)
        ewm_var = float(pd.Series(r).ewm(span=20).var().iloc[-1])
        if np.isnan(ewm_var) or ewm_var <= 0:
            ewm_var = float(np.var(r[-20:]))

        # steps일 예측
        sig2 = ewm_var
        var_unc = omega / max(1 - alpha - beta, 1e-6)
        for _ in range(steps):
            sig2 = omega + (alpha + beta) * sig2
            # 평균 회귀: 장기 분산으로 수렴
            sig2 = 0.7 * sig2 + 0.3 * var_unc

        return float(np.sqrt(max(sig2, 1e-8)))

    def run(self, df: pd.DataFrame, kelly_raw: float,
            vix_current: float, beta_profile) -> GARCHResult:
        result = GARCHResult(kelly_raw=kelly_raw)
        try:
            close = df['Close'].squeeze()
            rets  = close.pct_change().dropna().values

            if len(rets) < 30:
                result.kelly_final = kelly_raw
                return result

            # ── GARCH 파라미터 추정 ───────────────────────
            omega, alpha, beta_g = self._fit_garch(rets)

            # ── 5일 후 변동성 예측 ────────────────────────
            vol_daily  = self._forecast_vol(rets, omega, alpha, beta_g, steps=5)
            vol_annual = vol_daily * np.sqrt(252) * 100   # %

            # ── 변동성 퍼센타일 (과거 252일 기준) ─────────
            rolling_vol = pd.Series(rets).rolling(20).std().dropna().values
            if len(rolling_vol) > 10:
                pct = float(np.mean(rolling_vol <= vol_daily) * 100)
            else:
                pct = 50.0

            # ── 변동성 국면 분류 ──────────────────────────
            if vol_annual < 15:
                regime = "low"
            elif vol_annual < 30:
                regime = "normal"
            elif vol_annual < 50:
                regime = "high"
            else:
                regime = "extreme"

            # ── [방법 1] GARCH 스케일링 ───────────────────
            # 목표 변동성 / 예측 변동성 → Kelly 배수
            target_daily = self.TARGET_VOL / np.sqrt(252)
            scale_garch  = min(target_daily / (vol_daily + 1e-8), 2.0)
            kelly_garch  = round(kelly_raw * scale_garch, 1)

            # ── [방법 2] Risk Parity ──────────────────────
            # 목표 vol 달성을 위한 포지션 비중 직접 계산
            # position = target_vol / (vol_annual / 100)
            rp_position  = (self.TARGET_VOL / (vol_annual / 100 + 1e-8)) * 100
            kelly_rp     = round(min(kelly_raw, rp_position), 1)

            # ── [방법 3] VIX 교차 패널티 ─────────────────
            vix_mult = 1.0
            if vix_current >= 40:   vix_mult = 0.3
            elif vix_current >= 30: vix_mult = 0.5
            elif vix_current >= 25: vix_mult = 0.7
            elif vix_current >= 20: vix_mult = 0.85

            # ── 최종 Kelly: 세 방법 중 가장 보수적 ────────
            kelly_candidates = [kelly_garch, kelly_rp,
                                 kelly_raw * vix_mult * beta_profile.kelly_scale]
            kelly_final = round(max(0.0, min(kelly_candidates)), 1)

            # 국면별 상한
            max_kelly = {"low": 30., "normal": 20., "high": 12., "extreme": 5.}
            kelly_final = round(min(kelly_final, max_kelly[regime]), 1)

            result.vol_forecast     = round(vol_daily * 100, 3)
            result.vol_annualized   = round(vol_annual, 1)
            result.vol_regime       = regime
            result.kelly_raw        = kelly_raw
            result.kelly_garch      = kelly_garch
            result.kelly_riskparity = kelly_rp
            result.kelly_final      = kelly_final
            result.vol_percentile   = round(pct, 1)
            result.scaling_factor   = round(scale_garch, 3)
            result.success          = True

        except Exception as e:
            result.kelly_final = kelly_raw
            print(f"  ⚠️ GARCH: {e}")
        return result

@dataclass
class EngineBResult:
    pred_prices: list=field(default_factory=list)
    pred_rets: list=field(default_factory=list)
    price_p10: float=0.; price_p50: float=0.; price_p90: float=0.
    direction: str="HOLD"; dir_consistency: float=0.; val_loss: float=999.
    support_price: float=0.; resistance_price: float=0.; support_grade: str=""
    attention_weights: list=field(default_factory=list)
    attention_top3: list=field(default_factory=list)
    success: bool=False

@dataclass
class SectorResult:
    etf: str=""; ticker_rs: float=1.; sector_rs: float=1.
    sector_trend: str="neutral"; ticker_trend: str="neutral"; success: bool=False

@dataclass
class MTFResult:
    daily_rsi: float=50.; weekly_rsi: float=50.
    daily_trend: str="neutral"; weekly_trend: str="neutral"
    mtf_agree: bool=False; mtf_boost: float=0.; success: bool=False

@dataclass
class CircuitBreakerResult:
    vix: float=15.; dxy: float=100.; hyg_ret_20d: float=0.; spy_ret_5d: float=0.
    risk_count: int=0; triggered: bool=False; reason: str=""; success: bool=False

@dataclass
class DynamicStopResult:
    chandelier_stop: float=0.; psar_stop: float=0.; recommended_stop: float=0.
    trailing_path: list=field(default_factory=list); psar_trend: str="up"; success: bool=False

# [NEW A] 반등 포착 결과
@dataclass
class BounceResult:
    triggered: bool           = False   # 반등 조건 충족 여부
    signal_count: int         = 0       # 충족된 반등 신호 수
    signals: list             = field(default_factory=list)   # 신호 목록
    bounce_entry: float       = 0.      # 권장 반등 진입가
    bounce_stop: float        = 0.      # 반등 손절가
    bounce_target1: float     = 0.      # 1차 익절 (저항선 1)
    bounce_target2: float     = 0.      # 2차 익절 (저항선 2)
    expected_pct: float       = 0.      # 예상 반등 폭(%)
    dead_cat_risk: str        = "low"   # "low" | "medium" | "high"
    confidence: float         = 0.      # 반등 신뢰도 (0~100)
    success: bool             = False

# [NEW B] 숏 전략 결과
@dataclass
class ShortResult:
    triggered: bool           = False
    signal_count: int         = 0
    signals: list             = field(default_factory=list)
    short_entry: float        = 0.      # 숏 진입 권장가
    short_stop: float         = 0.      # 숏 손절 (위로)
    short_target1: float      = 0.      # 1차 익절 (지지선 1)
    short_target2: float      = 0.      # 2차 익절 (지지선 2)
    trend_type: str           = ""      # "trend_continuation" | "reversal"
    expected_drop_pct: float  = 0.
    confidence: float         = 0.
    success: bool             = False

# 거시 지표 캐시
@dataclass
class MacroData:
    vix: float=15.; dxy: float=100.; hyg_ret_20d: float=0.
    spy_ret_5d: float=0.; spy_close: Optional[pd.Series]=None
    success: bool=False


# ══════════════════════════════════════════════════════════════
#  Transformer 모델 (Attention 추출 포함, V15 동일)
# ══════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════
#  데이터 매니저
# ══════════════════════════════════════════════════════════════
class ZeusDataManager:
    def __init__(self, ticker: str):
        self.ticker=ticker.upper(); self.df=pd.DataFrame()
        self.spy_close=None; self.vix_data={}

    def fetch_all(self) -> bool:
        print(f"  📡 [{self.ticker}] 데이터 수집 중...")
        try:
            raw=yf.download(self.ticker,period="3y",interval="1d",progress=False)
            if raw.empty or len(raw)<150: print(f"  ❌ 데이터 부족"); return False
            if isinstance(raw.columns,pd.MultiIndex): raw.columns=raw.columns.get_level_values(0)
            self.df=raw[[c for c in ['Open','High','Low','Close','Volume'] if c in raw.columns]].copy()
        except Exception as e: print(f"  ❌ 다운로드 오류: {e}"); return False
        try:
            spy=yf.download("SPY",period="3y",interval="1d",progress=False)
            if isinstance(spy.columns,pd.MultiIndex): spy.columns=spy.columns.get_level_values(0)
            self.spy_close=spy['Close'].squeeze() if not spy.empty else None
        except: self.spy_close=None
        try:
            vix=yf.download("^VIX",period="3y",interval="1d",progress=False)
            if isinstance(vix.columns,pd.MultiIndex): vix.columns=vix.columns.get_level_values(0)
            if not vix.empty:
                self.vix_data={'series':vix['Close'].squeeze(),'current':float(vix['Close'].squeeze().iloc[-1]),'ok':True}
            else: self.vix_data={'ok':False,'current':15.}
        except: self.vix_data={'ok':False,'current':15.}
        print(f"  ✅ 로드 완료: {len(self.df)}일 ({self.df.index[0].date()} ~ {self.df.index[-1].date()})")
        return True

    def build_indicators(self) -> pd.DataFrame:
        df=self.df.copy()
        close=df['Close'].squeeze(); high=df['High'].squeeze()
        low=df['Low'].squeeze(); vol=df['Volume'].squeeze(); idx=df.index

        # RSI
        delta=close.diff(); ag=delta.clip(lower=0).ewm(alpha=1/14,adjust=False).mean()
        al=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
        df['RSI']=100-(100/(1+ag/al.replace(0,np.nan)))

        # ADX
        tr=pd.concat([(high-low),(high-close.shift()).abs(),(low-close.shift()).abs()],axis=1).max(axis=1)
        up_mv,dn_mv=high.diff(),-low.diff()
        pdm=pd.Series(np.where((up_mv>dn_mv)&(up_mv>0),up_mv,0.),index=idx)
        ndm=pd.Series(np.where((dn_mv>up_mv)&(dn_mv>0),dn_mv,0.),index=idx)
        tr_e=tr.ewm(alpha=1/14,adjust=False).mean()
        pdi=100*pdm.ewm(alpha=1/14,adjust=False).mean()/tr_e.replace(0,np.nan)
        ndi=100*ndm.ewm(alpha=1/14,adjust=False).mean()/tr_e.replace(0,np.nan)
        df['ADX']=((100*(pdi-ndi).abs()/(pdi+ndi).replace(0,np.nan)).ewm(alpha=1/14,adjust=False).mean())
        df['DI_diff']=pdi-ndi
        df['ATR']=tr.ewm(alpha=1/14,adjust=False).mean()

        # MACD
        e12=close.ewm(span=12,adjust=False).mean(); e26=close.ewm(span=26,adjust=False).mean()
        df['MACD']=e12-e26; df['MACD_Sig']=df['MACD'].ewm(span=9,adjust=False).mean()
        df['MACD_Hist']=df['MACD']-df['MACD_Sig']
        df['MACD_cross']=((df['MACD']>df['MACD_Sig'])&(df['MACD'].shift(1)<=df['MACD_Sig'].shift(1))).astype(float)

        # MFI
        tp=(high+low+close)/3; rmf=tp*vol
        df['MFI']=100-(100/(1+rmf.where(tp>tp.shift(1),0.).rolling(14).sum()/
                           rmf.where(tp<tp.shift(1),0.).rolling(14).sum().replace(0,np.nan)))

        # SMI
        h13=high.rolling(13).max(); l13=low.rolling(13).min(); mid=(h13+l13)/2
        ds=(close-mid).ewm(span=5,adjust=False).mean().ewm(span=5,adjust=False).mean()
        rs_=(h13-l13).ewm(span=5,adjust=False).mean().ewm(span=5,adjust=False).mean()
        df['SMI']=np.where(rs_!=0,(ds/(rs_/2+1e-8))*100,0.)

        # OBV
        obv_raw=(np.sign(close.diff().fillna(0))*vol).cumsum()
        df['OBV_norm']=(obv_raw-obv_raw.rolling(20).mean())/(obv_raw.rolling(20).std()+1e-8)

        # VWAP Gap
        vwap=(vol*(high+low+close)/3).cumsum()/vol.cumsum()
        df['VWAP_Gap']=(close-vwap)/(vwap+1e-8)

        # CMF
        mfv=((close-low)-(high-close))/(high-low).replace(0,1e-6)*vol
        df['CMF']=mfv.rolling(14).sum()/vol.rolling(14).sum()

        # BB
        bb_mid=close.rolling(20).mean(); bb_std=close.rolling(20).std()
        df['BB_Width']=(bb_std*4)/bb_mid.replace(0,np.nan)
        df['BB_Squeeze']=(df['BB_Width']<df['BB_Width'].rolling(50).quantile(0.2)).astype(float)
        df['BB_Lower']=bb_mid-2*bb_std; df['BB_Upper']=bb_mid+2*bb_std

        # RS vs SPY
        if self.spy_close is not None:
            spy=self.spy_close.reindex(close.index).ffill()
            df['RS']=(close/float(close.iloc[0]))/(spy/float(spy.iloc[0]))
        else: df['RS']=1.

        # 수익률
        df['Ret_1d']=close.pct_change(1); df['Ret_3d']=close.pct_change(3)
        df['Ret_5d']=close.pct_change(5); df['Ret_10d']=close.pct_change(10)
        df['Volatility']=df['Ret_1d'].rolling(20).std()
        df['Vol_Ratio']=vol/(vol.rolling(20).mean()+1e-8)

        # VIX 국면
        if self.vix_data.get('ok'):
            vix_s=self.vix_data['series'].reindex(close.index).ffill()
            df['VIX_regime']=pd.cut(vix_s,bins=[0,20,30,np.inf],labels=[0,1,2]).astype(float).fillna(0)
        else: df['VIX_regime']=0.

        # 매물대 피처
        wf=self._calc_wall_features_fast(close,vol)
        df['Wall_support_dist']=wf['support_dist']
        df['Wall_resistance_dist']=wf['resistance_dist']
        df['Wall_density_support']=wf['support_density']

        # VPA 지표
        df=self._add_vpa(df,close,high,low,vol)

        # 캔들 패턴 (반등 감지용)
        df=self._add_candle_patterns(df,open_=df['Open'].squeeze() if 'Open' in df.columns else close,
                                     close=close,high=high,low=low,vol=vol)

        return df.dropna()

    def _add_vpa(self,df,close,high,low,vol):
        # Force Index
        fi_raw=close.diff()*vol
        df['FI_13_norm']=(fi_raw.ewm(span=13,adjust=False).mean()-fi_raw.ewm(span=13,adjust=False).mean().rolling(50).mean())/(fi_raw.ewm(span=13,adjust=False).mean().rolling(50).std()+1e-8)
        df['FI_2']=fi_raw.ewm(span=2,adjust=False).mean()
        # EOM
        hl_mid=(high+low)/2; box=vol/(high-low+1e-8)
        eom=hl_mid.diff()/(box+1e-8)
        df['EOM_norm']=(eom.rolling(14).mean()-eom.rolling(14).mean().rolling(50).mean())/(eom.rolling(14).mean().rolling(50).std()+1e-8)
        # Up/Down Vol
        up_v=vol.where(close>=close.shift(1),0.); dn_v=vol.where(close<close.shift(1),0.)
        df['UD_Vol_Ratio']=up_v.rolling(14).sum()/(dn_v.rolling(14).sum()+1e-8)
        # PV Divergence
        pt=close.pct_change(5); vt=(vol/(vol.rolling(20).mean()+1e-8))-1
        df['PV_Divergence']=np.where(pt>0,-vt,vt)
        # Klinger
        tp=(high+low+close)/3
        tp_diff=tp-tp.shift(1)
        hl_range=high-low
        hl_safe=np.where(hl_range.values>0, hl_range.values, 1.0)   # pure ndarray
        sv=pd.Series(
            np.sign(tp_diff.fillna(0).values) * vol.values * 2 * (hl_range.values/hl_safe - 1),
            index=close.index
        )
        kvo_f=sv.ewm(span=34,adjust=False).mean(); kvo_s=sv.ewm(span=55,adjust=False).mean()
        kvo=kvo_f-kvo_s
        df['KVO_norm']=(kvo-kvo.rolling(50).mean())/(kvo.rolling(50).std()+1e-8)
        return df

    def _add_candle_patterns(self,df,open_,close,high,low,vol):
        """반등/반전 캔들 패턴 감지"""
        body=abs(close-open_)
        upper_wick=high-pd.concat([close,open_],axis=1).max(axis=1)
        lower_wick=pd.concat([close,open_],axis=1).min(axis=1)-low
        total_range=high-low+1e-8

        # 망치형 (Hammer): 아래 꼬리 길고, 몸통 작고, 아래 절반에 위치
        hammer_cond=((lower_wick/total_range>0.6) & (body/total_range<0.3) &
                     (upper_wick/total_range<0.1))
        df['Candle_Hammer']=hammer_cond.astype(float)

        # 도지 (Doji): 몸통이 매우 작음 → 결정 불확실, 반전 가능
        doji_cond=(body/total_range<0.1)
        df['Candle_Doji']=doji_cond.astype(float)

        # 불리시 인걸핑: 전날 하락 캔들을 현날 상승 캔들이 완전히 감쌈
        bullish_engulf=((close>open_) & (close.shift(1)<open_.shift(1)) &
                        (close>open_.shift(1)) & (open_<close.shift(1)))
        df['Candle_BullEngulf']=bullish_engulf.astype(float)

        # 거래량 급감 (패닉 셀링 소진 신호)
        df['Vol_Dry']=((vol/vol.rolling(20).mean())<0.6).astype(float)

        # 연속 하락 일수
        down_streak=pd.Series(0,index=close.index)
        for i in range(1,len(close)):
            if float(close.iloc[i])<float(close.iloc[i-1]):
                down_streak.iloc[i]=down_streak.iloc[i-1]+1
        df['Down_Streak']=down_streak

        return df

    def _calc_wall_features_fast(self,close,vol,window=60,n_bins=8):
        n=len(close); ca=close.values.astype('float64'); va=vol.values.astype('float64')
        sd=np.zeros(n); rd=np.zeros(n); se=np.zeros(n)
        for i in range(window,n):
            wc=ca[i-window:i]; wv=va[i-window:i]; curr=ca[i]; lo,hi=wc.min(),wc.max()
            if hi<=lo: continue
            counts,edges=np.histogram(wc,bins=n_bins,range=(lo,hi),weights=wv)
            total=counts.sum()+1e-8; mids=(edges[:-1]+edges[1:])/2
            sm=mids<=curr; rm=mids>curr
            if sm.any(): bi=np.argmax(counts*sm); sd[i]=(curr-mids[bi])/(curr+1e-8); se[i]=counts[bi]/total
            if rm.any(): bi=np.argmax(np.where(rm,counts,-1)); rd[i]=(mids[bi]-curr)/(curr+1e-8)
        return {'support_dist':pd.Series(sd,index=close.index),
                'resistance_dist':pd.Series(rd,index=close.index),
                'support_density':pd.Series(se,index=close.index)}

    def get_wall_snapshot(self) -> dict:
        v_df=self.df.tail(120).copy(); curr=float(v_df['Close'].iloc[-1])
        p_min,p_max=float(v_df['Close'].min()),float(v_df['Close'].max())
        rng=(p_max-p_min)/(p_min+1e-8)
        n_bins=8 if rng>1. else 10 if rng>0.5 else 12 if rng>0.2 else 15
        scale=15/n_bins; bins=np.linspace(p_min,p_max,n_bins+1)
        v_df['_bin']=pd.cut(v_df['Close'],bins=bins,include_lowest=True)
        profile=(v_df.groupby('_bin',observed=True)['Volume'].sum()/v_df['Volume'].sum())*100
        walls=[]
        for interval,dens in profile.items():
            mid=(interval.left+interval.right)/2
            if dens>25*scale: st="💎 다이아"
            elif dens>15*scale: st="🏢 강력"
            elif dens>8*scale: st="📄 보통"
            else: st="  얇음"
            walls.append({'price':round(mid,2),'density':round(float(dens),2),'status':st})
        wdf=pd.DataFrame(walls)
        below=wdf[wdf['price']<=curr].sort_values('price',ascending=False)
        above=wdf[wdf['price']>curr].sort_values('price',ascending=True)
        sup=below.iloc[0].to_dict() if not below.empty else {'price':p_min,'density':0,'status':'없음'}
        res=above.iloc[0].to_dict() if not above.empty else {'price':p_max,'density':0,'status':'없음'}
        # 2번째 지지/저항도 반환 (숏/반등 2차 목표용)
        sup2=below.iloc[1].to_dict() if len(below)>1 else sup
        res2=above.iloc[1].to_dict() if len(above)>1 else res
        return {'support':sup,'resistance':res,'support2':sup2,'resistance2':res2,'current':curr}


# ══════════════════════════════════════════════════════════════
#  거시 지표 수집
# ══════════════════════════════════════════════════════════════
class MacroFetcher:
    def fetch(self, vix_current: float, spy_close_3y: Optional[pd.Series]) -> MacroData:
        md = MacroData(vix=vix_current)
        md.spy_close = spy_close_3y

        # SPY 5일 수익률
        if spy_close_3y is not None and len(spy_close_3y) > 6:
            md.spy_ret_5d = float(spy_close_3y.iloc[-1]/spy_close_3y.iloc[-6]-1)

        try:
            dxy=yf.download("DX-Y.NYB",period="3mo",interval="1d",progress=False)
            if dxy.empty: dxy=yf.download("UUP",period="3mo",interval="1d",progress=False)
            if isinstance(dxy.columns,pd.MultiIndex): dxy.columns=dxy.columns.get_level_values(0)
            if not dxy.empty: md.dxy=float(dxy['Close'].squeeze().iloc[-1])
        except: pass

        try:
            hyg=yf.download("HYG",period="3mo",interval="1d",progress=False)
            if isinstance(hyg.columns,pd.MultiIndex): hyg.columns=hyg.columns.get_level_values(0)
            if not hyg.empty:
                hc=hyg['Close'].squeeze()
                md.hyg_ret_20d=float(hc.iloc[-1]/hc.iloc[max(0,len(hc)-21)]-1)
        except: pass

        md.success=True
        return md


# ══════════════════════════════════════════════════════════════
#  Circuit Breaker (V15와 동일, 거시 데이터 재사용)
# ══════════════════════════════════════════════════════════════
class CircuitBreaker:
    def run(self, cfg: ZeusConfig, macro: MacroData) -> CircuitBreakerResult:
        result=CircuitBreakerResult(vix=macro.vix,dxy=macro.dxy,
                                    hyg_ret_20d=macro.hyg_ret_20d,spy_ret_5d=macro.spy_ret_5d)
        reasons=[]
        if macro.vix>=cfg.vix_cb_threshold:
            result.risk_count+=1; reasons.append(f"VIX {macro.vix:.1f}")
        if macro.dxy>=cfg.dxy_cb_threshold:
            result.risk_count+=1; reasons.append(f"DXY {macro.dxy:.1f}")
        if macro.hyg_ret_20d<=cfg.hyg_drop_threshold:
            result.risk_count+=1; reasons.append(f"HYG {macro.hyg_ret_20d*100:.1f}%")
        if macro.spy_ret_5d<=-0.03:
            result.risk_count+=1; reasons.append(f"SPY 5일 {macro.spy_ret_5d*100:.1f}%")
        result.triggered=result.risk_count>=2
        result.reason=" | ".join(reasons) if reasons else "정상"
        result.success=True
        return result


# ══════════════════════════════════════════════════════════════
#  [NEW A] BounceEngine — 하락장 반등 포착 전용
# ══════════════════════════════════════════════════════════════
class BounceEngine:
    """
    하락장/스윙 구간에서 단기 반등 기회를 정밀하게 포착
    고베타 종목은 더 극단적 조건 요구 (Dead Cat 필터 강화)
    """
    def run(self, df: pd.DataFrame, wall: dict,
            beta: BetaProfile, mode: str) -> BounceResult:
        result=BounceResult()
        if mode not in ('swing','bear'): return result  # Bull 모드에선 실행 안 함

        try:
            s=df.iloc[-1]; curr=wall['current']
            close=df['Close'].squeeze(); high=df['High'].squeeze()
            low=df['Low'].squeeze(); vol=df['Volume'].squeeze()

            signals=[]
            confidence=0.

            # ── 신호 1: RSI 극단 과매도 ─────────────────────────
            rsi=float(s['RSI'])
            if rsi<=beta.rsi_oversold:
                severity="극단" if rsi<=15 else "강"
                signals.append(f"RSI {severity} 과매도 ({rsi:.1f})")
                confidence+=25 if rsi<=15 else 18

            # ── 신호 2: 연속 하락 소진 ──────────────────────────
            streak=int(s.get('Down_Streak',0))
            if streak>=3:
                signals.append(f"연속 하락 {streak}일 (소진 패턴)")
                confidence+=15 if streak>=5 else 10

            # ── 신호 3: 거래량 급감 (패닉셀 소진) ─────────────────
            if float(s.get('Vol_Dry',0))>0:
                signals.append("거래량 급감 (패닉 셀링 소진 신호)")
                confidence+=15

            # ── 신호 4: 망치형 캔들 ─────────────────────────────
            if float(s.get('Candle_Hammer',0))>0:
                signals.append("망치형 캔들 (하단 꼬리 반전 신호)")
                confidence+=20

            # ── 신호 5: 불리시 인걸핑 ────────────────────────────
            if float(s.get('Candle_BullEngulf',0))>0:
                signals.append("불리시 인걸핑 (세력 매집 신호)")
                confidence+=22

            # ── 신호 6: BB 하단 터치 ────────────────────────────
            if float(s.get('BB_Lower',curr*0.9))>0:
                bb_lower=float(s['BB_Lower']); bb_upper=float(s['BB_Upper'])
                if curr<=bb_lower*1.02:
                    signals.append(f"볼린저 하단 터치 (${bb_lower:.2f})")
                    confidence+=15

            # ── 신호 7: 매물대 지지선 근접 ───────────────────────
            sup=wall['support']['price']
            if sup>0 and abs(curr-sup)/curr<=0.015:
                signals.append(f"매물대 지지선 근접 ${sup:.2f} ({wall['support']['status']})")
                confidence+=20 if '다이아' in wall['support']['status'] else 10

            # ── 신호 8: VIX 스파이크 후 진정 조짐 ────────────────
            if float(s.get('VIX_regime',0))>=2:
                # VIX가 높은데 주가는 안 빠짐 → 반등 대기
                vix_regime=float(s['VIX_regime'])
                if float(s['Ret_1d'])>-0.01:  # 오늘 큰 추가 하락 없음
                    signals.append("VIX 공포 극점 + 가격 안정 → 반등 대기")
                    confidence+=12

            # ── 신호 9: Force Index 극단 음수 (매도 소진) ─────────
            fi=float(s.get('FI_13_norm',0))
            if fi<=-2.0:
                signals.append(f"Force Index 극단 매도 ({fi:.1f}σ) → 세력 매도 소진")
                confidence+=18

            # ── Dead Cat Bounce 리스크 판단 ──────────────────────
            # 진짜 반등 vs 잠깐 튀는 거 구분
            dead_cat_risk="low"
            dead_cat_reasons=[]

            # 거래량 없이 반등하면 Dead Cat 가능성 높음
            vol_ratio=float(s.get('Vol_Ratio',1.))
            if len(signals)>0 and vol_ratio<0.7:
                dead_cat_risk="high"
                dead_cat_reasons.append("반등 시 거래량 부족")

            # 하락 추세가 너무 강하면 (ADX>35 + 하락)
            adx=float(s.get('ADX',20)); di=float(s.get('DI_diff',0))
            if adx>35 and di<-10:
                dead_cat_risk="high" if dead_cat_risk!="low" else "medium"
                dead_cat_reasons.append(f"강한 하락 추세 (ADX {adx:.0f})")

            # 섹터 전체 붕괴 중
            if float(s.get('RS',1.))<0.7:
                dead_cat_risk="medium" if dead_cat_risk=="low" else dead_cat_risk
                dead_cat_reasons.append("종목 RS 극단 약세")

            # 고베타 종목은 Dead Cat 가중치 추가
            if beta.ticker_type=="high_beta" and dead_cat_risk!="low":
                dead_cat_risk="high"
                dead_cat_reasons.append("고베타 종목 Dead Cat 위험 가중")

            # 최종 판단
            result.signal_count=len(signals)
            result.signals=signals
            result.dead_cat_risk=dead_cat_risk

            # 충분한 신호 수 충족 + Dead Cat 아님
            min_sig=beta.bounce_min_signals
            if dead_cat_risk=="high": min_sig+=1   # Dead Cat 위험 높으면 더 많은 신호 요구

            if len(signals)>=min_sig and dead_cat_risk!="high":
                result.triggered=True

            # 진입가/손절/익절 계산
            atr=float(s['ATR'])
            result.bounce_entry=round(curr,2)
            result.bounce_stop =round(curr-beta.stop_atr_mult*atr,2)

            # 1차 익절: 직전 저항 (가장 가까운 매물대)
            result.bounce_target1=round(wall['resistance']['price'],2)
            # 2차 익절: 2번째 저항선
            result.bounce_target2=round(wall['resistance2']['price'],2)

            # 예상 반등 폭
            exp_pct=(result.bounce_target1/curr-1)*100
            result.expected_pct=round(exp_pct,1)

            # 최종 신뢰도 (Dead Cat 위험 패널티)
            if dead_cat_risk=="high": confidence*=0.4
            elif dead_cat_risk=="medium": confidence*=0.7
            result.confidence=round(min(confidence,90.),1)
            result.success=True

        except Exception as e:
            import traceback; print(f"  ⚠️  BounceEngine 오류: {e}"); traceback.print_exc()
        return result


# ══════════════════════════════════════════════════════════════
#  [NEW B] ShortEngine — 숏 전략 전용
# ══════════════════════════════════════════════════════════════
class ShortEngine:
    """
    모든 모드에서 SELL 신호 발생 시 실제 숏 전략으로 변환
    Bear/Swing 모드에선 독립적으로도 활성화
    """
    def run(self, df: pd.DataFrame, wall: dict,
            beta: BetaProfile, mode: str,
            eng_a_dir: str, eng_b_dir: str) -> ShortResult:
        result=ShortResult()
        # Bull 모드에서 두 엔진 모두 SELL이 아니면 실행 안 함
        if mode=='bull' and not (eng_a_dir=='SELL' and eng_b_dir=='SELL'):
            return result

        try:
            s=df.iloc[-1]; curr=wall['current']
            close=df['Close'].squeeze()

            signals=[]; confidence=0.

            # ── 신호 1: RSI 과매수 ──────────────────────────────
            rsi=float(s['RSI'])
            if rsi>=beta.rsi_overbought:
                signals.append(f"RSI 과매수 ({rsi:.1f} ≥ {beta.rsi_overbought:.0f})")
                confidence+=20

            # ── 신호 2: 저항선 근접 ─────────────────────────────
            res=wall['resistance']['price']
            if res>0 and abs(curr-res)/curr<=0.02:
                signals.append(f"저항선 근접 ${res:.2f} ({wall['resistance']['status']})")
                confidence+=22

            # ── 신호 3: 가짜 상승 (PV Divergence) ──────────────
            pv=float(s.get('PV_Divergence',0))
            if pv>=0.5:
                signals.append(f"거래량 감소 속 가격 상승 (PV Divergence {pv:.2f})")
                confidence+=20

            # ── 신호 4: MACD 데드크로스 ─────────────────────────
            macd=float(s.get('MACD',0)); sig=float(s.get('MACD_Sig',0))
            macd_prev=float(df['MACD'].iloc[-2]) if len(df)>1 else macd
            sig_prev=float(df['MACD_Sig'].iloc[-2]) if len(df)>1 else sig
            if macd<sig and macd_prev>=sig_prev:
                signals.append("MACD 데드크로스 (추세 전환 신호)")
                confidence+=15

            # ── 신호 5: ADX 강한 하락 추세 ──────────────────────
            adx=float(s.get('ADX',20)); di=float(s.get('DI_diff',0))
            if mode in ('swing','bear') and adx>25 and di<0:
                signals.append(f"강한 하락 추세 (ADX {adx:.0f}, DI- 우위)")
                confidence+=18

            # ── 신호 6: BB 상단 근접 + 수축 ─────────────────────
            if float(s.get('BB_Upper',0))>0:
                bb_upper=float(s['BB_Upper'])
                if curr>=bb_upper*0.99:
                    signals.append(f"BB 상단 돌파 (${bb_upper:.2f}) → 과열")
                    confidence+=15

            # ── 신호 7: Bear/Swing 모드 — 하락 추세 지속 ─────────
            if mode in ('swing','bear'):
                # 5일, 10일 모두 하락
                ret5=float(s.get('Ret_5d',0)); ret10=float(s.get('Ret_10d',0))
                if ret5<-0.05 and ret10<-0.08:
                    signals.append(f"중기 하락 추세 (5일 {ret5*100:.1f}%, 10일 {ret10*100:.1f}%)")
                    confidence+=15

            # ── 추세 유형 판단 ───────────────────────────────────
            # Trend Continuation: 하락 추세 중 반등 후 재하락
            # Reversal: 상승 추세 천장에서 반전
            adx=float(s.get('ADX',20))
            if mode in ('swing','bear') and adx>25:
                trend_type="trend_continuation"
                confidence+=5
            else:
                trend_type="reversal"

            # 최소 신호 기준
            result.signal_count=len(signals)
            result.signals=signals
            result.trend_type=trend_type

            min_signals=2 if mode in ('swing','bear') else 3
            if len(signals)>=min_signals and confidence>=beta.short_min_conf:
                result.triggered=True

            # 숏 진입/손절/익절 계산
            atr=float(s['ATR'])
            result.short_entry=round(curr,2)
            result.short_stop =round(curr+beta.stop_atr_mult*atr,2)   # 숏이므로 위로 손절

            # 1차 익절: 직전 지지선 (아래 매물대)
            result.short_target1=round(wall['support']['price'],2)
            # 2차 익절: 2번째 지지선
            result.short_target2=round(wall['support2']['price'],2)

            exp_drop=(curr-result.short_target1)/curr*100
            result.expected_drop_pct=round(exp_drop,1)
            result.confidence=round(min(confidence,90.),1)
            result.success=True

        except Exception as e:
            print(f"  ⚠️  ShortEngine 오류: {e}")
        return result


# ══════════════════════════════════════════════════════════════
#  섹터 분석 / MTF 분석 (V15 동일, 축약)
# ══════════════════════════════════════════════════════════════
class SectorAnalyzer:
    def run(self,ticker,spy_close):
        result=SectorResult(); etf=get_sector_etf(ticker); result.etf=etf
        try:
            raw=yf.download(etf,period="1y",interval="1d",progress=False)
            if raw.empty: return result
            if isinstance(raw.columns,pd.MultiIndex): raw.columns=raw.columns.get_level_values(0)
            ec=raw['Close'].squeeze()
            raw2=yf.download(ticker,period="1y",interval="1d",progress=False)
            if raw2.empty: return result
            if isinstance(raw2.columns,pd.MultiIndex): raw2.columns=raw2.columns.get_level_values(0)
            tc=raw2['Close'].squeeze(); common=ec.index.intersection(tc.index)
            if len(common)<20: return result
            ec=ec.reindex(common); tc=tc.reindex(common); w=min(63,len(common)-1)
            er=float(ec.iloc[-1]/ec.iloc[-w]-1); tr=float(tc.iloc[-1]/tc.iloc[-w]-1)
            result.ticker_rs=round(tr/(abs(er)+1e-8) if er!=0 else 1.,3)
            if spy_close is not None:
                sc=spy_close.reindex(common).ffill(); sr=float(sc.iloc[-1]/sc.iloc[-w]-1)
                result.sector_rs=round(er/(abs(sr)+1e-8) if sr!=0 else 1.,3)
            es20=ec.rolling(20).mean().iloc[-1]; es50=ec.rolling(50).mean().iloc[-1]
            ts20=tc.rolling(20).mean().iloc[-1]; ts50=tc.rolling(50).mean().iloc[-1]
            result.sector_trend=("bullish" if float(ec.iloc[-1])>float(es20)>float(es50) else "bearish" if float(ec.iloc[-1])<float(es20)<float(es50) else "neutral")
            result.ticker_trend=("bullish" if float(tc.iloc[-1])>float(ts20)>float(ts50) else "bearish" if float(tc.iloc[-1])<float(ts20)<float(ts50) else "neutral")
            result.success=True
            print(f"  ✅ 섹터: 종목RS={result.ticker_rs:.2f} 섹터RS={result.sector_rs:.2f}")
        except Exception as e: print(f"  ⚠️ 섹터: {e}")
        return result

class MTFAnalyzer:
    def _rsi(self,c,p=14):
        d=c.diff(); g=d.clip(lower=0).ewm(alpha=1/p,adjust=False).mean()
        l=(-d.clip(upper=0)).ewm(alpha=1/p,adjust=False).mean()
        return round(float((100-(100/(1+g/l.replace(0,np.nan)))).iloc[-1]),1)
    def _macd_h(self,c):
        m=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean()
        return float((m-m.ewm(span=9,adjust=False).mean()).iloc[-1])
    def _trend(self,c):
        if len(c)<50: return "neutral"
        s20=float(c.rolling(20).mean().iloc[-1]); s50=float(c.rolling(50).mean().iloc[-1]); cu=float(c.iloc[-1])
        return "up" if cu>s20>s50 else "down" if cu<s20<s50 else "neutral"
    def run(self,ticker):
        result=MTFResult()
        try:
            rd=yf.download(ticker,period="2y",interval="1d",progress=False)
            rw=yf.download(ticker,period="5y",interval="1wk",progress=False)
            for r in [rd,rw]:
                if isinstance(r.columns,pd.MultiIndex): r.columns=r.columns.get_level_values(0)
            if rd.empty or rw.empty or len(rd)<50 or len(rw)<30: return result
            cd=rd['Close'].squeeze(); cw=rw['Close'].squeeze()
            result.daily_rsi=self._rsi(cd); result.weekly_rsi=self._rsi(cw)
            result.daily_trend=self._trend(cd); result.weekly_trend=self._trend(cw)
            def _dir(t,mh,r): return "up" if t=="up" and mh>0 else "down" if t=="down" and mh<0 else "up" if r>60 and mh>0 else "down" if r<40 and mh<0 else "neutral"
            dd=_dir(result.daily_trend,self._macd_h(cd),result.daily_rsi)
            wd=_dir(result.weekly_trend,self._macd_h(cw),result.weekly_rsi)
            result.mtf_agree=(dd==wd and dd!="neutral")
            result.mtf_boost=12. if result.mtf_agree and dd=="up" else -8. if result.mtf_agree else 0. if "neutral" in [dd,wd] else -10.
            result.success=True
            print(f"  ✅ MTF: 일봉 {dd} / 주봉 {wd}")
        except Exception as e: print(f"  ⚠️ MTF: {e}")
        return result


# ══════════════════════════════════════════════════════════════
#  Engine A — ML 앙상블
# ══════════════════════════════════════════════════════════════
class EngineA_ML:
    def __init__(self,config): self.cfg=config

    def _meta_learn(self, model_defs, val_probs_list, now_probs_list,
                    val_accs, X_tr, y_tr, X_val, y_val,
                    X_now, train_df, selected, df):
        """
        MetaLearner: 각 기본 모델의 예측 확률 + 시장 국면 피처를 입력으로
        GBM 메타 모델이 최적 앙상블 가중치를 동적으로 결정.

        국면 피처 예시:
          - VIX 레짐 (0/1/2)
          - 현재 변동성 vs 20일 평균 변동성 비율
          - ADX (추세 강도)
          - BB 수축 여부
          - 5일 수익률 (모멘텀)
        """
        try:
            # ── 국면 피처 컬럼 정의 ──────────────────────────────
            regime_feats = ['VIX_regime', 'Volatility', 'ADX', 'BB_Squeeze', 'Ret_5d']
            available    = [f for f in regime_feats if f in train_df.columns]

            # ── 검증셋 메타 피처 구성 ────────────────────────────
            # [각 모델 예측확률 ...] + [국면 피처 ...]
            val_preds_arr  = np.column_stack(val_probs_list)   # (n_val, n_models)
            n_val          = len(y_val)
            val_regime_raw = train_df[available].values[-n_val:] if available else np.zeros((n_val, 1))
            # 국면 피처 표준화
            sc_regime = StandardScaler()
            val_regime = sc_regime.fit_transform(val_regime_raw)
            X_meta_val = np.hstack([val_preds_arr, val_regime])

            # ── 학습셋 메타 피처 구성 ────────────────────────────
            # 각 기본 모델의 훈련셋 out-of-fold 예측 생성
            n_tr = len(y_tr)
            oof_preds = np.zeros((n_tr, len(model_defs)))
            for fold_tr, fold_val in TimeSeriesSplit(n_splits=3).split(X_tr):
                for mi, (name, pipe) in enumerate(model_defs.items()):
                    from sklearn.pipeline import Pipeline as _Pipe
                    p2 = _Pipe(pipe.steps)
                    p2.fit(X_tr[fold_tr], y_tr[fold_tr])
                    oof_preds[fold_val, mi] = p2.predict_proba(X_tr[fold_val])[:, 1]

            tr_regime_raw = train_df[available].values[:n_tr] if available else np.zeros((n_tr, 1))
            tr_regime     = sc_regime.transform(tr_regime_raw) if available else tr_regime_raw
            X_meta_tr     = np.hstack([oof_preds, tr_regime])

            # ── MetaLearner (GBM) 학습 ───────────────────────────
            meta_model = GradientBoostingClassifier(
                n_estimators=100, max_depth=2,
                learning_rate=0.05, subsample=0.8,
                min_samples_leaf=5, random_state=42
            )
            # 유효한 OOF 행만 사용
            valid_mask = np.any(oof_preds != 0, axis=1)
            if valid_mask.sum() < 20:
                raise ValueError("OOF 샘플 부족")
            meta_model.fit(X_meta_tr[valid_mask], y_tr[valid_mask])

            meta_acc = accuracy_score(
                y_val, meta_model.predict(X_meta_val)
            )
            print(f"     ✔ MetaLearner {meta_acc*100:.1f}%")

            # ── 현재 시점 예측 ───────────────────────────────────
            now_preds_arr  = np.array(now_probs_list).reshape(1, -1)
            now_regime_raw = df[available].iloc[[-1]].values if available else np.zeros((1, 1))
            now_regime     = sc_regime.transform(now_regime_raw)
            X_meta_now     = np.hstack([now_preds_arr, now_regime])

            prob_up = float(meta_model.predict_proba(X_meta_now)[0][1])

            # ── 모델 기여도 (피처 중요도 기반) ───────────────────
            fi = meta_model.feature_importances_
            model_names = list(model_defs.keys())
            model_contribs = {n: round(float(fi[i]), 3) for i, n in enumerate(model_names)}
            model_weights  = model_contribs

            print(f"     모델 기여도: " +
                  "  ".join(f"{n}={v:.2f}" for n, v in model_weights.items()))

            return prob_up, model_weights

        except Exception as e:
            # MetaLearner 실패 시 기존 정확도 가중평균으로 폴백
            print(f"     ⚠️ MetaLearner 실패 ({e}) → 정확도 가중평균으로 대체")
            acc_v = np.array(list(val_accs.values()))
            wts   = np.maximum(acc_v - 0.5, 0.01); wts /= wts.sum()
            mw    = {n: round(float(w), 3) for n, w in zip(val_accs.keys(), wts)}
            pu    = float(np.dot(wts, now_probs_list))
            return pu, mw

    def _perm_select(self,X,y,names):
        try:
            probe=Pipeline([("sc",StandardScaler()),("clf",GradientBoostingClassifier(n_estimators=100,max_depth=3,random_state=42))])
            sp=int(len(X)*0.8); probe.fit(X[:sp],y[:sp])
            pi=permutation_importance(probe,X[sp:],y[sp:],n_repeats=5,random_state=42,scoring='accuracy')
            imp=pi.importances_mean; thr=np.percentile(imp,25)
            sel=[n for n,v in zip(names,imp) if v>=thr]
            if len(sel)<5: sel=names
            print(f"  🔍 피처: {len(names)}→{len(sel)}개"); return sel
        except: return names

    def _opt_horizon(self,df,features):
        cfg=self.cfg; close=df['Close'].squeeze(); best_days,best_acc=cfg.prediction_day_candidates[0],0.
        for days in cfg.prediction_day_candidates:
            try:
                ret=close.shift(-days)/close-1
                lbl=pd.Series(np.where(ret>cfg.label_dead_zone,1,np.where(ret<-cfg.label_dead_zone,0,np.nan)),index=df.index)
                tmp=df.copy(); tmp['_y']=lbl; tmp=tmp.dropna(subset=['_y']+features).iloc[:-days]
                if len(tmp)<80: continue
                X,y=tmp[features].values,tmp['_y'].values.astype(int); accs=[]
                for tr_i,vi in TimeSeriesSplit(n_splits=3).split(X):
                    p=Pipeline([("sc",StandardScaler()),("clf",GradientBoostingClassifier(n_estimators=100,max_depth=3,random_state=42))])
                    p.fit(X[tr_i],y[tr_i]); accs.append(accuracy_score(y[vi],p.predict(X[vi])))
                avg=float(np.mean(accs))*100
                if avg>best_acc: best_acc,best_days=avg,days
            except: continue
        print(f"  ✅ 최적: {best_days}일 ({best_acc:.1f}%)"); return best_days

    def run(self,df,vix_current,mode='bull'):
        result=EngineAResult(); cfg=self.cfg
        try:
            all_features=['RSI','ADX','DI_diff','MFI','MACD','MACD_Hist','MACD_cross',
                          'SMI','RS','BB_Width','BB_Squeeze','OBV_norm','CMF','VWAP_Gap',
                          'Vol_Ratio','Ret_1d','Ret_3d','Ret_5d','Ret_10d','Volatility',
                          'VIX_regime','Wall_support_dist','Wall_resistance_dist','Wall_density_support',
                          'FI_13_norm','EOM_norm','UD_Vol_Ratio','PV_Divergence','KVO_norm',
                          'Down_Streak','Candle_Hammer','Candle_BullEngulf']
            # Bear/Swing 모드: 하락 반전 피처 더 강조 (label_dead_zone 완화)
            effective_dead_zone=cfg.label_dead_zone
            if mode=='bear': effective_dead_zone=0.01   # 더 작은 움직임도 신호로 잡음

            optimal_days=self._opt_horizon(df,all_features)
            close=df['Close'].squeeze()
            ret=close.shift(-optimal_days)/close-1
            labels=pd.Series(np.where(ret>effective_dead_zone,1,np.where(ret<-effective_dead_zone,0,np.nan)),index=df.index)
            df2=df.copy(); df2['Target']=labels
            train_df=df2.dropna(subset=['Target']+all_features).iloc[:-optimal_days]
            predict_row=df[all_features].iloc[[-1]]
            if len(train_df)<80: print("  ⚠️ 학습 부족"); return result

            X_all=train_df[all_features].values; y_all=train_df['Target'].values.astype(int)
            selected=self._perm_select(X_all,y_all,all_features)
            X_train=train_df[selected].values; y_train=train_df['Target'].values.astype(int)
            X_now=predict_row[selected].values

            regime="fear" if vix_current>=30 else "volatile" if vix_current>=20 else "normal"
            reg_map={"normal":0,"volatile":1,"fear":2}
            mask=train_df['VIX_regime'].values==reg_map[regime]; cnt=int(mask.sum())
            X_reg=X_train[mask] if cnt>=60 else X_train; y_reg=y_train[mask] if cnt>=60 else y_train
            sp=int(len(X_reg)*0.8)
            X_tr,X_val=X_reg[:sp],X_reg[sp:]; y_tr,y_val=y_reg[:sp],y_reg[sp:]

            model_defs={
                "GBM":Pipeline([("sc",StandardScaler()),("clf",GradientBoostingClassifier(n_estimators=300,learning_rate=0.03,max_depth=4,subsample=0.8,min_samples_leaf=5,random_state=42))]),
                "RF": Pipeline([("sc",StandardScaler()),("clf",RandomForestClassifier(n_estimators=300,max_depth=7,min_samples_leaf=3,random_state=42))]),
                "MLP":Pipeline([("sc",StandardScaler()),("clf",MLPClassifier(hidden_layer_sizes=(128,64,32),max_iter=500,early_stopping=True,validation_fraction=0.15,random_state=42))]),
            }
            if XGBOOST_OK:
                model_defs["XGB"]=Pipeline([("sc",StandardScaler()),("clf",XGBClassifier(n_estimators=300,learning_rate=0.03,max_depth=4,subsample=0.8,eval_metric='logloss',random_state=42,verbosity=0))])

            val_accs,val_probs_list,now_probs_list={},[],[]
            print("  🤖 [Engine A] 1단계 기본 모델 학습 중...")
            for name,pipe in model_defs.items():
                pipe.fit(X_tr,y_tr); acc=accuracy_score(y_val,pipe.predict(X_val))
                val_accs[name]=acc; val_probs_list.append(pipe.predict_proba(X_val)[:,1])
                now_probs_list.append(pipe.predict_proba(X_now)[0][1])
                print(f"     ✔ {name} {acc*100:.1f}%")

            # ── [NEW 2] MetaLearner — 시장 국면 인식 앙상블 ──────
            # 각 모델의 예측 확률 + 시장 국면 피처 → MetaLearner가
            # "지금 국면에서 어떤 모델을 얼마나 믿을지" 동적으로 결정
            print("  🧠 [MetaLearner] 2단계 메타 앙상블 학습 중...")
            prob_up, model_weights = self._meta_learn(
                model_defs, val_probs_list, now_probs_list,
                val_accs, X_tr, y_tr, X_val, y_val,
                X_now, train_df, selected, df
            )

            tscv=TimeSeriesSplit(n_splits=cfg.cv_folds); cv_scores=[]
            for tr_i,vi in tscv.split(X_train):
                fp=[]
                for name,pipe in model_defs.items():
                    p2=Pipeline(pipe.steps); p2.fit(X_train[tr_i],y_train[tr_i])
                    fp.append(p2.predict_proba(X_train[vi])[:,1])
                # MetaLearner로 교체됐으므로 CV는 단순 평균 다수결로 계산
                ens=(np.mean(fp, axis=0)>=0.5).astype(int)
                cv_scores.append(accuracy_score(y_train[vi],ens))
            cv_acc=round(float(np.mean(cv_scores))*100,1); cv_std=round(float(np.std(cv_scores))*100,1)
            print(f"  ✅ CV: {cv_acc:.1f}% ± {cv_std:.1f}%")

            direction="BUY" if prob_up>=cfg.buy_prob_threshold else "SELL" if prob_up<=cfg.sell_prob_threshold else "HOLD"
            b=cfg.take_profit_pct/cfg.stop_loss_pct
            kelly_pct=round(max(0.,(prob_up*b-(1-prob_up))/b)*100,1)
            if cv_std>10: kelly_pct=round(kelly_pct*0.5,1)
            atr=float(df['ATR'].iloc[-1]); cp=float(df['Close'].iloc[-1])
            result.prob_up=round(prob_up*100,1); result.direction=direction
            result.cv_accuracy=cv_acc; result.cv_std=cv_std; result.kelly_pct=kelly_pct
            result.optimal_days=optimal_days; result.regime=regime; result.model_weights=model_weights
            result.selected_features=selected
            result.stop_price=round(cp-2.*atr,2); result.target_price=round(cp+4.*atr,2)
            result.success=True
        except Exception as e:
            import traceback; print(f"  ❌ Engine A: {e}"); traceback.print_exc()
        return result


# ══════════════════════════════════════════════════════════════
#  Engine B — MLP 회귀 (torch 없이 동작)
#  Transformer → sklearn MLPRegressor 대체
#  · P10/P50/P90, 몬테카를로, 방향 판단 동일하게 유지
#  · Attention → 피처 중요도(Permutation Importance)로 대체
# ══════════════════════════════════════════════════════════════
class EngineB_DL:
    def __init__(self,config): self.cfg=config

    def _feat_importance(self, model, X_val, y_val, feature_cols):
        try:
            from sklearn.inspection import permutation_importance as pi_fn
            pi = pi_fn(model, X_val, y_val, n_repeats=5,
                       random_state=42, scoring='neg_mean_squared_error')
            imp = pi.importances_mean
            top_idx = np.argsort(imp)[::-1][:3]
            feat_desc = {
                'Ret_1d':'전일 수익률','Volatility':'변동성','OBV_norm':'OBV 강도',
                'RSI':'RSI','CMF':'자금흐름(CMF)','VWAP_Gap':'VWAP 괴리',
                'MACD_Hist':'MACD 히스토그램','Wall_support_dist':'지지선 거리',
                'Wall_resistance_dist':'저항선 거리','FI_13_norm':'Force Index',
                'UD_Vol_Ratio':'상승/하락 거래량비','PV_Divergence':'PV 다이버전스',
            }
            top3 = []
            for rank, idx in enumerate(top_idx):
                fname = feature_cols[idx] if idx < len(feature_cols) else f"feat{idx}"
                desc  = feat_desc.get(fname, fname)
                pct   = float(abs(imp[idx])) * 100
                top3.append({'rank':rank+1,'days_ago':0,'weight':round(pct,1),
                             'char':f"피처 중요도 #{rank+1}: {desc} ({pct:.1f}%)"})
            return [], top3
        except:
            return [], []

    def run(self,df,wall):
        result=EngineBResult(); cfg=self.cfg
        try:
            fc=['Ret_1d','Volatility','OBV_norm','RSI','CMF','VWAP_Gap',
                'MACD_Hist','Wall_support_dist','Wall_resistance_dist',
                'FI_13_norm','UD_Vol_Ratio','PV_Divergence']
            ret_idx = fc.index('Ret_1d')

            rd = df[fc].values.astype('float32')
            n  = len(rd)
            if n < cfg.lookback + cfg.forecast + 30:
                return result

            sc = MinMaxScaler()
            rd_sc = sc.fit_transform(rd)

            # 슬라이딩 윈도우 → flatten
            X_list, y_list = [], []
            for i in range(cfg.lookback, n - cfg.forecast):
                X_list.append(rd_sc[i-cfg.lookback:i].flatten())
                y_list.append(rd_sc[i:i+cfg.forecast, ret_idx])

            X_arr = np.array(X_list, dtype='float32')
            y_arr = np.array(y_list, dtype='float32')
            sp = int(len(X_arr) * 0.8)
            X_tr, X_val = X_arr[:sp], X_arr[sp:]
            y_tr, y_val = y_arr[:sp], y_arr[sp:]

            if len(X_tr) < 20: return result

            print("  🧠 [Engine B] MLP 회귀 학습 중...")
            models = []
            for d in range(cfg.forecast):
                m = MLPRegressor(hidden_layer_sizes=(128,64,32), max_iter=300,
                                 early_stopping=True, validation_fraction=0.15,
                                 random_state=42, learning_rate_init=0.001)
                m.fit(X_tr, y_tr[:,d])
                models.append(m)

            val_losses = [float(np.mean((m.predict(X_val)-y_val[:,d])**2))
                          for d,m in enumerate(models)]
            avg_val_loss = float(np.mean(val_losses))
            print(f"  ✅ MLP val_loss={avg_val_loss:.6f}")

            last_x = rd_sc[-cfg.lookback:].flatten().reshape(1,-1)
            pred_rets_sc = np.array([m.predict(last_x)[0] for m in models])

            inv_dummy = np.zeros((cfg.forecast, len(fc)), dtype='float32')
            inv_dummy[:, ret_idx] = pred_rets_sc
            pred_rets = sc.inverse_transform(inv_dummy)[:, ret_idx]

            cp = float(df['Close'].iloc[-1])
            pp = [cp]
            for r in pred_rets: pp.append(pp[-1]*(1+r))
            pp = pp[1:]

            hv = float(df['Volatility'].iloc[-1]); np.random.seed(42)
            mc = cp*np.exp(np.cumsum(
                pred_rets[np.newaxis,:]+np.random.normal(0,hv,(cfg.mc_simulations,cfg.forecast)),axis=1))
            fp = mc[:,-1]

            result.pred_prices      = pp
            result.pred_rets        = list(pred_rets)
            result.price_p10        = round(float(np.percentile(fp,10)),2)
            result.price_p50        = round(float(np.percentile(fp,50)),2)
            result.price_p90        = round(float(np.percentile(fp,90)),2)
            result.dir_consistency  = float(abs(np.mean(np.sign(pred_rets))))
            result.direction        = "BUY" if result.price_p50>cp else "SELL"
            result.val_loss         = avg_val_loss
            result.support_price    = wall['support']['price']
            result.resistance_price = wall['resistance']['price']
            result.support_grade    = wall['support']['status']
            result.attention_weights, result.attention_top3 = \
                self._feat_importance(models[-1], X_val, y_val[:,-1], fc)
            result.success = True
        except Exception as e:
            import traceback; print(f"  ❌ Engine B: {e}"); traceback.print_exc()
        return result


# ══════════════════════════════════════════════════════════════
#  Dynamic Stop (V15 동일)
# ══════════════════════════════════════════════════════════════
class DynamicStopCalculator:
    def run(self,df,beta,pred_prices):
        result=DynamicStopResult()
        try:
            close=df['Close'].squeeze(); high=df['High'].squeeze(); atr=df['ATR'].squeeze()
            curr=float(close.iloc[-1]); mult=beta.chandelier_mult
            ch_exit=high.rolling(22).max()-mult*atr; ch_now=float(ch_exit.iloc[-1])
            # Parabolic SAR
            af0,afs,afm=0.02,0.02,0.20
            sar=np.zeros(len(close)); ep=np.zeros(len(close)); af=np.zeros(len(close)); bull=np.ones(len(close),bool)
            ca,ha,la=close.values,high.values,df['Low'].values
            sar[0]=float(la[0]); ep[0]=float(ha[0]); af[0]=af0
            for i in range(1,len(ca)):
                ns=sar[i-1]+af[i-1]*(ep[i-1]-sar[i-1])
                if bull[i-1]:
                    ns=min(ns,la[i-1],la[max(0,i-2)])
                    if la[i]<ns:
                        bull[i]=False; ns=ep[i-1]; ep[i]=la[i]; af[i]=af0
                    else:
                        bull[i]=True; ep[i]=max(ep[i-1],ha[i])
                        af[i]=min(af[i-1]+afs,afm) if ha[i]>ep[i-1] else af[i-1]
                else:
                    ns=max(ns,ha[i-1],ha[max(0,i-2)])
                    if ha[i]>ns:
                        bull[i]=True; ns=ep[i-1]; ep[i]=ha[i]; af[i]=af0
                    else:
                        bull[i]=False; ep[i]=min(ep[i-1],la[i])
                        af[i]=min(af[i-1]+afs,afm) if la[i]<ep[i-1] else af[i-1]
                sar[i]=ns
            pn=float(sar[-1]); pt="up" if bool(bull[-1]) else "down"
            vc=ch_now if ch_now<curr else curr*0.95; vp=pn if pn<curr else curr*0.95
            rec=max(vc,vp); result.chandelier_stop=round(ch_now,2)
            result.psar_stop=round(pn,2); result.recommended_stop=round(rec,2)
            result.psar_trend=pt
            atr_v=float(atr.iloc[-1]); rh=curr; trail=[]
            for pp in pred_prices:
                rh=max(rh,pp); trail.append(round(rh-mult*atr_v,2))
            result.trailing_path=trail; result.success=True
        except Exception as e: print(f"  ⚠️ DynStop: {e}")
        return result


# ══════════════════════════════════════════════════════════════
#  [NEW B] SignalLogger — 신호 기록 + 승률 자동 추적
# ══════════════════════════════════════════════════════════════
LOG_FILE = "zeus_log.csv"
LOG_FIELDS = [
    "log_id", "date", "ticker", "mode", "signal", "confidence",
    "entry_price", "stop_price", "target_price", "kelly_pct",
    "horizon_days", "result_price", "actual_ret_pct", "win", "reviewed"
]

class SignalLogger:
    """
    실행할 때마다 신호를 CSV에 저장.
    --review 실행 시 과거 신호의 horizon_days 후 실제 가격을 자동으로 채워 승률 계산.
    """
    def __init__(self, log_path: str = LOG_FILE):
        self.log_path = log_path
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=LOG_FIELDS).writeheader()

    def _next_id(self) -> int:
        rows = self._load_all()
        return max([int(r.get("log_id", 0)) for r in rows], default=0) + 1

    def _load_all(self) -> list:
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                return list(csv.DictReader(f))
        except: return []

    def _save_all(self, rows: list):
        with open(self.log_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
            w.writeheader(); w.writerows(rows)

    def save(self, ticker: str, mode: str, signal: str, confidence: float,
             entry: float, stop: float, target: float,
             kelly: float, horizon: int) -> int:
        """신호 1건 저장. log_id 반환."""
        lid = self._next_id()
        row = {
            "log_id": lid,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "ticker": ticker.upper(),
            "mode": mode,
            "signal": signal,
            "confidence": round(confidence, 1),
            "entry_price": round(entry, 4),
            "stop_price": round(stop, 4),
            "target_price": round(target, 4),
            "kelly_pct": round(kelly, 1),
            "horizon_days": horizon,
            "result_price": "",
            "actual_ret_pct": "",
            "win": "",
            "reviewed": "N",
        }
        with open(self.log_path, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=LOG_FIELDS).writerow(row)
        return lid

    def review(self):
        """
        미검토(reviewed=N) 신호 중 horizon_days 이상 경과한 건에 대해
        현재 가격을 yfinance로 받아 실제 수익률·승패를 자동 기입.
        """
        rows = self._load_all()
        updated = 0
        today = datetime.today().date()
        pending = [r for r in rows if r.get("reviewed","N") == "N"]
        print(f"\n  📋 미검토 신호: {len(pending)}건")

        for r in rows:
            if r.get("reviewed", "N") != "N": continue
            sig_date = datetime.strptime(r["date"], "%Y-%m-%d").date()
            horizon = int(r.get("horizon_days", 5))
            target_date = sig_date + timedelta(days=horizon + 3)   # 주말 여유
            if today < target_date: continue

            ticker = r["ticker"]
            try:
                raw = yf.download(ticker, period="1mo", interval="1d", progress=False)
                if raw.empty: continue
                if isinstance(raw.columns, pd.MultiIndex):
                    raw.columns = raw.columns.get_level_values(0)
                close = raw["Close"].squeeze()
                # horizon_days 이후 가장 가까운 거래일 종가 사용
                result_price = float(close.iloc[min(horizon, len(close)-1)])
                entry = float(r["entry_price"])
                signal = r["signal"]
                ret = (result_price / entry - 1) * 100
                # 숏 신호면 방향 반전
                if "SHORT" in signal: ret = -ret
                win = "1" if ret > 0 else "0"

                r["result_price"] = round(result_price, 4)
                r["actual_ret_pct"] = round(ret, 2)
                r["win"] = win
                r["reviewed"] = "Y"
                updated += 1
                direction = "📈" if ret > 0 else "📉"
                print(f"  {direction} [{ticker}] {r['date']} {signal:20s} → {ret:+.2f}%")
            except Exception as e:
                print(f"  ⚠️ [{ticker}] 검토 실패: {e}")

        self._save_all(rows)
        print(f"  ✅ {updated}건 업데이트 완료  →  {self.log_path}")

    def stats(self):
        """
        검토 완료(reviewed=Y) 신호 기준으로 종목별·모드별 통계 출력.
        """
        rows = [r for r in self._load_all() if r.get("reviewed") == "Y"]
        if not rows:
            print("\n  ⚠️ 검토 완료된 신호가 없습니다. --review 를 먼저 실행하세요.")
            return

        total = len(rows)
        wins = sum(1 for r in rows if r.get("win") == "1")
        rets = [float(r["actual_ret_pct"]) for r in rows if r["actual_ret_pct"] != ""]
        avg_ret = float(np.mean(rets)) if rets else 0.
        win_rate = wins / total * 100 if total else 0.

        W = 64
        print(f"\n{'━'*W}")
        print(f"  📊 ZEUS 신호 누적 통계  ({self.log_path})")
        print(f"{'─'*W}")
        print(f"  총 신호: {total}건  |  승률: {win_rate:.1f}%  |  평균 수익: {avg_ret:+.2f}%")

        # 최대 수익 / 최대 손실
        if rets:
            print(f"  최대 수익: {max(rets):+.2f}%  |  최대 손실: {min(rets):+.2f}%")
            # Sharpe 근사 (단순)
            std_r = float(np.std(rets)) + 1e-8
            sharpe = avg_ret / std_r
            print(f"  수익 표준편차: {std_r:.2f}%  |  Sharpe(근사): {sharpe:.2f}")

        # 종목별 통계
        print(f"\n{'─'*W}")
        print(f"  {'티커':<8} {'신호수':>5} {'승률':>7} {'평균수익':>9}")
        tickers = sorted(set(r["ticker"] for r in rows))
        for t in tickers:
            sub = [r for r in rows if r["ticker"] == t]
            w = sum(1 for r in sub if r.get("win") == "1")
            sub_rets = [float(r["actual_ret_pct"]) for r in sub if r["actual_ret_pct"]]
            wr = w / len(sub) * 100
            ar = float(np.mean(sub_rets)) if sub_rets else 0.
            bar_w = int(wr / 5)
            bar = "█" * bar_w + "░" * (20 - bar_w)
            print(f"  {t:<8} {len(sub):>5}건  {wr:>5.1f}%  {ar:>+8.2f}%  [{bar}]")

        # 모드별 통계
        print(f"\n{'─'*W}")
        print(f"  {'모드':<8} {'신호수':>5} {'승률':>7} {'평균수익':>9}")
        for m in ["bull", "swing", "bear"]:
            sub = [r for r in rows if r.get("mode", "").lower() == m]
            if not sub: continue
            w = sum(1 for r in sub if r.get("win") == "1")
            sub_rets = [float(r["actual_ret_pct"]) for r in sub if r["actual_ret_pct"]]
            wr = w / len(sub) * 100
            ar = float(np.mean(sub_rets)) if sub_rets else 0.
            emoji = {"bull":"🐂","swing":"⚡","bear":"🐻"}.get(m,"")
            print(f"  {emoji}{m:<7} {len(sub):>5}건  {wr:>5.1f}%  {ar:>+8.2f}%")

        # 신호 타입별
        print(f"\n{'─'*W}")
        sig_types = sorted(set(r["signal"] for r in rows))
        print(f"  {'신호':30s} {'건수':>4} {'승률':>7} {'평균수익':>9}")
        for st in sig_types:
            sub = [r for r in rows if r["signal"] == st]
            w = sum(1 for r in sub if r.get("win") == "1")
            sub_rets = [float(r["actual_ret_pct"]) for r in sub if r["actual_ret_pct"]]
            wr = w / len(sub) * 100
            ar = float(np.mean(sub_rets)) if sub_rets else 0.
            print(f"  {st:30s} {len(sub):>4}건  {wr:>5.1f}%  {ar:>+8.2f}%")

        print(f"{'━'*W}\n")


# ══════════════════════════════════════════════════════════════
#  [NEW A] Backtester — 과거 신호 승률 검증
# ══════════════════════════════════════════════════════════════
@dataclass
class BacktestTrade:
    date: str = ""
    signal: str = ""
    mode: str = ""
    entry: float = 0.
    stop: float = 0.
    target: float = 0.
    exit_price: float = 0.
    ret_pct: float = 0.
    exit_reason: str = ""   # "target" | "stop" | "time"
    win: bool = False

@dataclass
class BacktestResult:
    ticker: str = ""
    trades: list = field(default_factory=list)
    total: int = 0
    wins: int = 0
    win_rate: float = 0.
    avg_ret: float = 0.
    max_win: float = 0.
    max_loss: float = 0.
    sharpe: float = 0.
    max_drawdown: float = 0.
    profit_factor: float = 0.
    mode_stats: dict = field(default_factory=dict)
    success: bool = False


class Backtester:
    """
    실제 과거 데이터를 슬라이딩 윈도우로 잘라서
    각 구간에 Zeus의 간소화 신호 로직을 적용 → 실제 수익 계산.

    ⚠️ 주의: Engine A (ML 재학습) + Engine B (Transformer 재학습)를
    매 구간마다 full 실행하면 수 시간이 걸리므로,
    백테스터에서는 "기술지표 기반 규칙 신호"만 사용합니다.
    (실제 Zeus와 동일한 판단은 아니지만 신호 방향성 검증에 충분)
    """

    def __init__(self, ticker: str, period_years: int = 1,
                 hold_days: int = 5, stop_pct: float = 0.05,
                 target_pct: float = 0.15):
        self.ticker = ticker.upper()
        self.period_years = period_years
        self.hold_days = hold_days
        self.stop_pct = stop_pct
        self.target_pct = target_pct

    def _rule_signal(self, row: pd.Series, prev: pd.Series) -> str:
        """
        기술지표 기반 간소화 신호.
        BUY  조건: RSI<35 + MACD히스토그램 상승 + ADX>20 + OBV_norm>-0.5
        SELL 조건: RSI>70 + MACD히스토그램 하락 + ADX>20
        BOUNCE: RSI<25 + Down_Streak>=3 + Candle_Hammer
        SHORT:  RSI>75 + PV_Divergence>0.5 + MACD데드크로스
        """
        rsi  = float(row.get("RSI", 50))
        adx  = float(row.get("ADX", 15))
        mh   = float(row.get("MACD_Hist", 0))
        mh_p = float(prev.get("MACD_Hist", 0)) if prev is not None else mh
        obv  = float(row.get("OBV_norm", 0))
        pv   = float(row.get("PV_Divergence", 0))
        ds   = float(row.get("Down_Streak", 0))
        ham  = float(row.get("Candle_Hammer", 0))
        vix  = float(row.get("VIX_regime", 0))

        # 장 국면
        mode = "bear" if vix >= 2 else "swing" if vix >= 1 else "bull"

        if mode == "bull":
            if rsi < 35 and mh > mh_p and adx > 20 and obv > -0.5:
                return "BUY"
            if rsi > 70 and mh < mh_p and adx > 20:
                return "SELL"
        elif mode in ("swing", "bear"):
            if rsi < 25 and ds >= 3 and ham > 0:
                return "BOUNCE"
            if rsi > 75 and pv > 0.5 and mh < mh_p:
                return "SHORT"
            if rsi < 35 and mh > mh_p and adx > 20:
                return "BUY"
        return "HOLD"

    def _mode_from_row(self, row: pd.Series) -> str:
        vix = float(row.get("VIX_regime", 0))
        return "bear" if vix >= 2 else "swing" if vix >= 1 else "bull"

    def _simulate_trade(self, close_arr: np.ndarray,
                        entry_idx: int, signal: str,
                        entry_price: float) -> BacktestTrade:
        """
        entry_idx 이후 최대 hold_days 동안 포지션 유지.
        stop / target 먼저 닿으면 그날 종가로 청산.
        """
        is_short = (signal in ("SELL", "SHORT"))
        stop   = entry_price * (1 + self.stop_pct   * ( 1 if is_short else -1))
        target = entry_price * (1 + self.target_pct * (-1 if is_short else  1))

        exit_price = entry_price
        exit_reason = "time"
        end_idx = min(entry_idx + self.hold_days, len(close_arr) - 1)

        for j in range(entry_idx + 1, end_idx + 1):
            p = close_arr[j]
            if not is_short:
                if p <= stop:
                    exit_price = stop;   exit_reason = "stop";   break
                if p >= target:
                    exit_price = target; exit_reason = "target"; break
            else:
                if p >= stop:
                    exit_price = stop;   exit_reason = "stop";   break
                if p <= target:
                    exit_price = target; exit_reason = "target"; break
        else:
            exit_price = close_arr[end_idx]

        ret = (exit_price / entry_price - 1) * 100
        if is_short: ret = -ret
        return BacktestTrade(
            entry=round(entry_price, 4), stop=round(stop, 4),
            target=round(target, 4), exit_price=round(exit_price, 4),
            ret_pct=round(ret, 2), exit_reason=exit_reason,
            signal=signal, win=(ret > 0)
        )

    def run(self, df: pd.DataFrame) -> BacktestResult:
        result = BacktestResult(ticker=self.ticker)
        W = 64
        print(f"\n{'━'*W}")
        print(f"  📊 [BACKTEST] {self.ticker}  |  과거 {self.period_years}년  hold={self.hold_days}일")
        print(f"  손절 {self.stop_pct*100:.0f}%  |  익절 {self.target_pct*100:.0f}%")
        print(f"{'─'*W}")

        if len(df) < 60:
            print("  ❌ 데이터 부족 — 백테스트 불가"); return result

        close = df["Close"].squeeze().values.astype(float)
        dates = df.index.tolist()
        trades: List[BacktestTrade] = []
        last_exit_idx = -1   # 포지션 겹침 방지

        mode_counts: Dict[str, Dict[str, int]] = {
            m: {"total": 0, "win": 0} for m in ["bull", "swing", "bear"]
        }

        for i in range(1, len(df) - self.hold_days - 1):
            if i <= last_exit_idx:
                continue   # 이전 트레이드 보유 중

            row  = df.iloc[i]
            prev = df.iloc[i-1]
            sig  = self._rule_signal(row, prev)
            mode = self._mode_from_row(row)

            if sig == "HOLD": continue

            t = self._simulate_trade(close, i, sig, close[i])
            t.date = str(dates[i].date()) if hasattr(dates[i], "date") else str(dates[i])[:10]
            t.mode = mode
            trades.append(t)
            last_exit_idx = i + self.hold_days

            mode_counts[mode]["total"] += 1
            if t.win: mode_counts[mode]["win"] += 1

        if not trades:
            print("  ⚠️ 유효 신호 없음"); return result

        rets = [t.ret_pct for t in trades]
        wins = [t for t in trades if t.win]
        losses = [t for t in trades if not t.win]

        result.total     = len(trades)
        result.wins      = len(wins)
        result.win_rate  = len(wins) / len(trades) * 100
        result.avg_ret   = float(np.mean(rets))
        result.max_win   = max(rets)
        result.max_loss  = min(rets)
        result.sharpe    = result.avg_ret / (float(np.std(rets)) + 1e-8)

        # Max Drawdown (누적 수익 곡선 기준)
        eq = np.cumprod([1 + r/100 for r in rets])
        peak = np.maximum.accumulate(eq)
        dd = (eq - peak) / (peak + 1e-8) * 100
        result.max_drawdown = float(dd.min())

        # Profit Factor
        gross_win  = sum(t.ret_pct for t in wins)  if wins   else 0.
        gross_loss = sum(abs(t.ret_pct) for t in losses) if losses else 1e-8
        result.profit_factor = gross_win / gross_loss
        result.mode_stats = mode_counts
        result.trades = trades
        result.success = True

        # ── 출력 ─────────────────────────────────────────────
        print(f"  총 신호: {result.total}건  |  승률: {result.win_rate:.1f}%  |  평균수익: {result.avg_ret:+.2f}%")
        print(f"  최대 수익: {result.max_win:+.2f}%  |  최대 손실: {result.max_loss:+.2f}%")
        print(f"  Max Drawdown: {result.max_drawdown:.2f}%  |  Profit Factor: {result.profit_factor:.2f}  |  Sharpe: {result.sharpe:.2f}")

        print(f"\n  {'모드':<8} {'신호':>5} {'승률':>7}")
        for m, mc in mode_counts.items():
            if mc["total"] == 0: continue
            wr = mc["win"] / mc["total"] * 100
            emoji = {"bull":"🐂","swing":"⚡","bear":"🐻"}.get(m,"")
            print(f"  {emoji}{m:<7} {mc['total']:>5}건  {wr:>5.1f}%")

        print(f"\n  최근 10건 거래 내역:")
        print(f"  {'날짜':<12} {'신호':<10} {'진입':>8} {'청산':>8} {'수익':>8} {'사유':<8} {'모드'}")
        for t in trades[-10:]:
            icon = "✅" if t.win else "❌"
            print(f"  {t.date:<12} {t.signal:<10} ${t.entry:>7.2f} ${t.exit_price:>7.2f} {t.ret_pct:>+7.2f}% {t.exit_reason:<8} {t.mode}  {icon}")

        # 승률 바
        bar_w = int(result.win_rate / 5)
        bar = "█" * bar_w + "░" * (20 - bar_w)
        verdict = ("✅ 유효한 전략" if result.win_rate >= 55 and result.profit_factor >= 1.2
                   else "⚠️ 개선 필요" if result.win_rate >= 45
                   else "❌ 이 종목에선 부적합")
        print(f"\n  승률 [{bar}] {result.win_rate:.1f}%  →  {verdict}")
        print(f"{'━'*W}")

        return result


# ══════════════════════════════════════════════════════════════
#  ZEUS ULTIMATE V17 — 메인 실행
# ══════════════════════════════════════════════════════════════
def run_zeus_v17(ticker: str, config: ZeusConfig = None,
                 run_backtest: bool = False,
                 logger: 'SignalLogger' = None):
    cfg=config or ZeusConfig()
    W=72

    print(f"\n{'━'*W}")
    print(f"  ⚡ ZEUS ULTIMATE V18  |  {ticker}  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  🖥️  Engine B: MLP(sklearn)  |  XGBoost: {'✅' if XGBOOST_OK else '❌'}")
    print(f"{'━'*W}")

    # ── 데이터 수집 ───────────────────────────────────────────
    dm=ZeusDataManager(ticker)
    if not dm.fetch_all(): return
    df=dm.build_indicators(); wall=dm.get_wall_snapshot(); vix=dm.vix_data.get('current',15.)
    if df.empty or len(df)<100: print("  ❌ 데이터 부족"); return

    # ── [NEW A] 백테스트 (--backtest 옵션 시) ─────────────────
    if run_backtest:
        bt = Backtester(ticker, period_years=1, hold_days=5,
                        stop_pct=0.05, target_pct=0.15)
        bt.run(df)

    # ── 거시 지표 수집 ────────────────────────────────────────
    print(f"\n{'─'*W}")
    print(f"  🌐 [MACRO] 거시 지표 수집")
    print(f"{'─'*W}")
    macro=MacroFetcher().fetch(vix,dm.spy_close)
    cb=CircuitBreaker().run(cfg,macro)

    # ── [CORE] 시장 모드 결정 ─────────────────────────────────
    mode=MarketRegimeDetector().detect(macro.vix,macro.spy_ret_5d,macro.hyg_ret_20d,macro.dxy)

    # ── [NEW C] 베타 프로파일 ─────────────────────────────────
    beta=get_beta_profile(ticker)

    # 모드 출력
    mode_emoji={"bull":"🐂 BULL MODE","swing":"⚡ SWING MODE","bear":"🐻 BEAR MODE"}
    mode_desc={"bull":"상승장 — 기본 전략 (BUY 우선)",
               "swing":"변동장 — 반등 + 숏 혼용 전략",
               "bear":"하락장 — 반등 포착 + 숏 공격 전략"}
    print(f"\n{'━'*W}")
    print(f"  🎛️  현재 모드: {mode_emoji[mode]}")
    print(f"  📋 전략 방향: {mode_desc[mode]}")
    print(f"  🔬 종목 타입: {beta.ticker_type.upper()}")
    print(f"     손절배수 {beta.stop_atr_mult}×ATR  켈리스케일 {beta.kelly_scale}×  최소반등신호 {beta.bounce_min_signals}개")
    print(f"{'━'*W}")

    # ── 섹터 / MTF ────────────────────────────────────────────
    print(f"\n{'─'*W}"); print(f"  🏭 [SECTOR] 섹터 분석"); print(f"{'─'*W}")
    sector=SectorAnalyzer().run(ticker,dm.spy_close)
    print(f"\n{'─'*W}"); print(f"  📅 [MTF] 멀티 타임프레임"); print(f"{'─'*W}")
    mtf=MTFAnalyzer().run(ticker)

    # ── Engine A ──────────────────────────────────────────────
    print(f"\n{'─'*W}"); print(f"  🤖 [ENGINE A] ML 앙상블"); print(f"{'─'*W}")
    eng_a=EngineA_ML(cfg).run(df,vix,mode)

    # ── Engine B ──────────────────────────────────────────────
    print(f"\n{'─'*W}"); print(f"  🧠 [ENGINE B] Transformer"); print(f"{'─'*W}")
    eng_b=EngineB_DL(cfg).run(df,wall)

    # ── Dynamic Stop ──────────────────────────────────────────
    dyn_stop=DynamicStopResult()
    if eng_b.success: dyn_stop=DynamicStopCalculator().run(df,beta,eng_b.pred_prices)

    # ── [NEW A] Bounce Engine (Swing/Bear 모드) ───────────────
    bounce=BounceResult()
    if mode in ('swing','bear'):
        print(f"\n{'─'*W}"); print(f"  ⚡ [BOUNCE] 반등 포착 분석"); print(f"{'─'*W}")
        bounce=BounceEngine().run(df,wall,beta,mode)

    # ── [NEW B] Short Engine ──────────────────────────────────
    a_dir=eng_a.direction if eng_a.success else "HOLD"
    b_dir=eng_b.direction if eng_b.success else "HOLD"
    print(f"\n{'─'*W}"); print(f"  🐻 [SHORT] 숏 전략 분석"); print(f"{'─'*W}")
    short=ShortEngine().run(df,wall,beta,mode,a_dir,b_dir)

    curr=wall['current']; s=df.iloc[-1]

    def pbar(p,w=22):
        f=int(p/100*w); return f"[{'█'*f}{'░'*(w-f)}] {p:.1f}%"
    def mbar(p,w=20):
        f=int(p/100*w); return f"{'▓'*f}{'░'*(w-f)}"

    # ════════════════════════════════════════════════════════════
    #  출력 섹션
    # ════════════════════════════════════════════════════════════

    # Circuit Breaker
    print(f"\n{'─'*W}"); print(f"  🛡️  [CIRCUIT BREAKER]"); print(f"{'─'*W}")
    cb_st="🚨 발동" if cb.triggered else ("⚠️ 주의" if cb.risk_count==1 else "✅ 정상")
    print(f"  상태: {cb_st}  ({cb.risk_count}/4)  |  VIX {cb.vix:.1f}  DXY {cb.dxy:.1f}  HYG {cb.hyg_ret_20d*100:+.1f}%  SPY5일 {cb.spy_ret_5d*100:+.1f}%")
    if cb.triggered: print(f"  ⛔ 원인: {cb.reason}")

    # 기술적 지표
    print(f"\n{'─'*W}"); print(f"  📊 [L1] 기술적 지표"); print(f"{'─'*W}")
    print(f"  현재가 ${curr:,.2f}  RSI {float(s['RSI']):.1f}  ADX {float(s['ADX']):.1f}  MFI {float(s['MFI']):.1f}  MACD_Hist {float(s['MACD_Hist']):+.4f}")
    print(f"  CMF {float(s['CMF']):+.4f}  OBV {float(s['OBV_norm']):+.2f}σ  RS(SPY) {float(s['RS']):.3f}  ATR ${float(s['ATR']):.2f}  변동성 {float(s['Volatility'])*100:.2f}%")
    print(f"  BB {'🧨 압축' if s['BB_Squeeze']>0 else '발산'}  연속하락 {int(s.get('Down_Streak',0))}일  Hammer {'✅' if s.get('Candle_Hammer',0)>0 else '—'}  BullEngulf {'✅' if s.get('Candle_BullEngulf',0)>0 else '—'}")

    # VPA
    print(f"\n{'─'*W}"); print(f"  🔍 [VPA] 거래량 분석"); print(f"{'─'*W}")
    fi=float(s['FI_13_norm']); ud=float(s['UD_Vol_Ratio']); pv=float(s['PV_Divergence']); kvo=float(s['KVO_norm'])
    print(f"  Force Index {fi:+.2f}σ  ({'🐂 매수세력' if fi>1.5 else '🐻 매도세력' if fi<-1.5 else '중립'})")
    print(f"  Up/Down Vol {ud:.2f}x   ({'📈 매집' if ud>1.3 else '📉 분산' if ud<0.8 else '중립'})")
    print(f"  PV Diverg   {pv:+.3f}   ({'⚠️ 가짜상승' if pv>0.5 else '✅ 거래량 동반' if pv<-0.3 else '중립'})")
    print(f"  Klinger     {kvo:+.2f}σ  ({'🐂 유입' if kvo>1. else '🐻 유출' if kvo<-1. else '중립'})")
    vpa_bull=sum([fi>1.,float(s['EOM_norm'])>0.5,ud>1.2,pv<-0.2,kvo>0.5])
    vpa_bear=sum([fi<-1.,float(s['EOM_norm'])<-0.5,ud<0.9,pv>0.5,kvo<-0.5])
    vpa_label=f"🔥 강한 매집 ({vpa_bull}/5)" if vpa_bull>=3 else f"💧 강한 분산 ({vpa_bear}/5)" if vpa_bear>=3 else f"↔ 혼조 ({vpa_bull}강/{vpa_bear}약)"
    print(f"  종합: {vpa_label}")

    # 매물대
    print(f"\n{'─'*W}"); print(f"  📦 [매물대]"); print(f"{'─'*W}")
    print(f"  지지1 ${wall['support']['price']:,.2f} {wall['support']['status']}  ·  지지2 ${wall['support2']['price']:,.2f}")
    print(f"  저항1 ${wall['resistance']['price']:,.2f} {wall['resistance']['status']}  ·  저항2 ${wall['resistance2']['price']:,.2f}")

    # 섹터 / MTF
    print(f"\n{'─'*W}"); print(f"  🏭 [SECTOR]  📅 [MTF]"); print(f"{'─'*W}")
    if sector.success:
        tk={"bullish":"📈 강세","bearish":"📉 약세","neutral":"↔ 중립"}
        print(f"  섹터 {sector.etf}: 종목RS {sector.ticker_rs:.2f}  섹터RS {sector.sector_rs:.2f}  섹터추세 {tk.get(sector.sector_trend,'중립')}  종목추세 {tk.get(sector.ticker_trend,'중립')}")
    if mtf.success:
        print(f"  MTF: 일봉RSI {mtf.daily_rsi:.1f}({mtf.daily_trend})  주봉RSI {mtf.weekly_rsi:.1f}({mtf.weekly_trend})  일치 {'✅' if mtf.mtf_agree else '❌'} (보정 {mtf.mtf_boost:+.0f}점)")

    # Engine A
    print(f"\n{'─'*W}"); print(f"  🤖 [ENGINE A]"); print(f"{'─'*W}")
    if eng_a.success:
        print(f"  {eng_a.optimal_days}일 예측  |  국면: {eng_a.regime}  |  가중치: {eng_a.model_weights}")
        print(f"  상승확률: {pbar(eng_a.prob_up)}")
        print(f"  CV: {pbar(eng_a.cv_accuracy)} ±{eng_a.cv_std:.1f}%  방향: {eng_a.direction}  켈리: {eng_a.kelly_pct:.1f}%")
    else: print("  ⚠️ Engine A 실패")

    # Engine B + Attention
    print(f"\n{'─'*W}"); print(f"  🧠 [ENGINE B]"); print(f"{'─'*W}")
    if eng_b.success:
        print(f"  P10 ${eng_b.price_p10:,.2f}  P50 ${eng_b.price_p50:,.2f}  P90 ${eng_b.price_p90:,.2f}  방향: {eng_b.direction}  일관성: {eng_b.dir_consistency*100:.0f}%")
        print(f"  {'Day':<5} {'Price':>8} {'Change':>8}")
        for i,(p,r) in enumerate(zip(eng_b.pred_prices,eng_b.pred_rets)):
            chg=(p/curr-1)*100
            print(f"  Day{i+1:<2}  ${p:>8.2f}  {chg:>+7.2f}%")
        if eng_b.attention_top3:
            print(f"\n  🔬 피처 중요도 (예측 기여도 상위):")
            for it in eng_b.attention_top3:
                print(f"  #{it['rank']} {it['char']}")
    else: print("  ⚠️ Engine B 실패")

    # [NEW A] 반등 포착 결과
    if mode in ('swing','bear'):
        print(f"\n{'─'*W}")
        print(f"  ⚡ [BOUNCE ENGINE] 반등 포착")
        print(f"{'─'*W}")
        dc_emoji={"low":"✅ 낮음","medium":"⚠️ 보통","high":"🚨 높음"}
        if bounce.success:
            print(f"  반등 신호 : {bounce.signal_count}개 감지  |  Dead Cat 위험: {dc_emoji.get(bounce.dead_cat_risk,'?')}")
            for sg in bounce.signals:
                print(f"    ✓ {sg}")
            if bounce.triggered:
                rr=(bounce.bounce_target1-bounce.bounce_entry)/(bounce.bounce_entry-bounce.bounce_stop) if bounce.bounce_entry>bounce.bounce_stop else 0
                print(f"\n  ⚡ 반등 진입 권장!")
                print(f"  진입가   : ${bounce.bounce_entry:,.2f}")
                print(f"  손절가   : ${bounce.bounce_stop:,.2f}  ({(bounce.bounce_entry-bounce.bounce_stop)/bounce.bounce_entry*100:.1f}%)")
                print(f"  1차 익절 : ${bounce.bounce_target1:,.2f}  ({bounce.expected_pct:+.1f}%)")
                print(f"  2차 익절 : ${bounce.bounce_target2:,.2f}")
                print(f"  손익비   : 1:{rr:.1f}  |  신뢰도: {pbar(bounce.confidence)}")
            else:
                print(f"\n  ⏳ 반등 조건 미충족 ({bounce.signal_count}/{beta.bounce_min_signals}개)")
                if bounce.dead_cat_risk=="high":
                    print(f"  🚨 Dead Cat 위험 높음 — 추가 신호 확인 필요")
        else:
            print("  ⚠️  반등 분석 실패")

    # [NEW B] 숏 전략 결과
    print(f"\n{'─'*W}")
    print(f"  🐻 [SHORT ENGINE] 숏 전략")
    print(f"{'─'*W}")
    if short.success:
        trend_k={"trend_continuation":"추세 지속형","reversal":"추세 반전형"}
        print(f"  숏 신호: {short.signal_count}개  |  타입: {trend_k.get(short.trend_type,'?')}  |  신뢰도: {short.confidence:.0f}%")
        for sg in short.signals:
            print(f"    ✓ {sg}")
        if short.triggered:
            rr=(short.short_entry-short.short_target1)/(short.short_stop-short.short_entry) if short.short_stop>short.short_entry else 0
            print(f"\n  🐻 숏 진입 권장!")
            print(f"  진입가   : ${short.short_entry:,.2f}")
            print(f"  손절가   : ${short.short_stop:,.2f}  (위로 {(short.short_stop-short.short_entry)/short.short_entry*100:.1f}%)")
            print(f"  1차 익절 : ${short.short_target1:,.2f}  ({-short.expected_drop_pct:.1f}% 하락)")
            print(f"  2차 익절 : ${short.short_target2:,.2f}")
            print(f"  손익비   : 1:{rr:.1f}  |  신뢰도: {pbar(short.confidence)}")
        else:
            print(f"  — 숏 조건 미충족 ({short.signal_count}개)")
    else:
        print("  — 숏 분석 실패")

    # Dynamic Stop
    print(f"\n{'─'*W}"); print(f"  📉 [DYNAMIC STOP]"); print(f"{'─'*W}")
    if dyn_stop.success:
        print(f"  Chandelier ${dyn_stop.chandelier_stop:,.2f}  |  PSAR ${dyn_stop.psar_stop:,.2f} ({dyn_stop.psar_trend})  |  권장 ${dyn_stop.recommended_stop:,.2f}")
        if dyn_stop.trailing_path:
            print(f"  트레일링: Day1 ${dyn_stop.trailing_path[0]:,.2f} → Day{len(dyn_stop.trailing_path)} ${dyn_stop.trailing_path[-1]:,.2f}")

    # ══════════════════════════════════════════════════════════
    #  FUSION — 모드별 최종 통합 신호
    # ══════════════════════════════════════════════════════════
    print(f"\n{'━'*W}")
    print(f"  ⚡ [FUSION V18] 최종 통합 신호  —  {mode.upper()} MODE")
    print(f"{'─'*W}")

    # 로그 저장용 기본값 (엔진 실패 시 대비)
    final      = "⚖️ [HOLD]"
    fused_conf = eng_a.cv_accuracy if eng_a.success else 0.
    garch      = GARCHResult()   # 기본값 (엔진 실패 대비)

    if eng_a.success and eng_b.success:
        agree=(a_dir==b_dir and a_dir!="HOLD")

        # 통합 신뢰도
        mse_sc=float(np.clip(85.+np.log10(max(eng_b.val_loss,1e-8))*12,30.,85.))
        avg_v=float(df['Volatility'].std()); cur_v=float(s['Volatility'])
        vola_pen=min((cur_v/(avg_v+1e-8))*8.,20.)
        wall_bon=min(wall['support']['density']/5.,8.)
        dir_bon=eng_b.dir_consistency*8.
        ag_bon=cfg.fusion_agreement_bonus if agree else -10.
        cv_bon=(eng_a.cv_accuracy-50.)*0.3
        sec_bon=0.
        if sector.success:
            if sector.sector_trend==sector.ticker_trend=="bullish": sec_bon=+8.
            elif sector.sector_trend=="bearish" or sector.ticker_trend=="bearish": sec_bon=-6.
            if sector.ticker_rs>1.2: sec_bon+=4.
            elif sector.ticker_rs<0.8: sec_bon-=4.
        mtf_bon=mtf.mtf_boost if mtf.success else 0.
        vpa_bon=float(np.clip((vpa_bull-vpa_bear)*2.,-10.,10.))

        fused_conf=float(np.clip(mse_sc+dir_bon+wall_bon-vola_pen+ag_bon+cv_bon+sec_bon+mtf_bon+vpa_bon,30.,95.))

        print(f"  Engine A: {a_dir} (확률 {eng_a.prob_up:.1f}%)  ·  Engine B: {b_dir} (P50 ${eng_b.price_p50:,.2f})")
        print(f"  VPA {vpa_bon:+.0f}점  섹터 {sec_bon:+.0f}점  MTF {mtf_bon:+.0f}점  CV {cv_bon:+.0f}점")
        print(f"  통합 신뢰도: {pbar(fused_conf)}")
        print()

        # ── 모드별 최종 판단 ──────────────────────────────────
        if mode=='bull':
            # 기존 V15 로직
            if cb.triggered:
                final="🚨 [강제 HOLD] Circuit Breaker 발동"
            elif not agree:
                final="⚖️ [HOLD] 엔진 불일치"
            elif a_dir=="BUY":
                if eng_a.prob_up>=65 and float(s['ADX'])>25 and float(s['DI_diff'])>0 and fused_conf>=70 and vpa_bull>=3:
                    final="🚀 [PERFECT BUY] 전 조건 충족 + VPA 매집 확인"
                elif eng_a.prob_up>=58 and fused_conf>=60:
                    final="📈 [BUY 고려] 강세 신호 우세"
                else:
                    final="📈 [BUY 후보] 추가 확인 필요"
            elif a_dir=="SELL":
                if short.triggered:
                    final=f"🐻 [SELL+숏] 하락 신호 + 숏 진입 권장 (신뢰도 {short.confidence:.0f}%)"
                else:
                    final="📉 [SELL 후보] 약세 신호"
            else:
                final="⚖️ [HOLD]"

        elif mode=='swing':
            # 롱/숏/반등 혼용
            if not agree and bounce.triggered and not short.triggered:
                final=f"⚡ [BOUNCE LONG] 반등 포착 (신뢰도 {bounce.confidence:.0f}%)  손익비 1:{((bounce.bounce_target1-bounce.bounce_entry)/(bounce.bounce_entry-bounce.bounce_stop+1e-8)):.1f}"
            elif short.triggered and not bounce.triggered:
                final=f"🐻 [SHORT] 숏 진입 권장 (신뢰도 {short.confidence:.0f}%)  손익비 1:{((short.short_entry-short.short_target1)/(short.short_stop-short.short_entry+1e-8)):.1f}"
            elif agree and a_dir=="BUY" and fused_conf>=60 and not cb.triggered:
                final="📈 [BUY] 스윙 모드 롱 진입 (두 엔진 일치)"
            elif agree and a_dir=="SELL" and short.triggered:
                final=f"🐻 [SHORT] 스윙 모드 숏 (두 엔진 일치 + 숏 신호)"
            elif bounce.triggered and short.triggered:
                final="⚖️ [대기] 반등 vs 숏 신호 충돌 — 방향 확인 후 진입"
            else:
                final="⚖️ [대기] 명확한 방향성 없음"

        else:  # bear mode
            if bounce.triggered and bounce.dead_cat_risk!="high" and bounce.confidence>=55:
                rr_b=(bounce.bounce_target1-bounce.bounce_entry)/(bounce.bounce_entry-bounce.bounce_stop+1e-8)
                final=f"⚡ [BEAR BOUNCE] 하락장 반등 포착 (신뢰도 {bounce.confidence:.0f}%  손익비 1:{rr_b:.1f})"
                if beta.ticker_type=="high_beta":
                    final+="  ⚠️ 고베타 — 포지션 절반 이하"
            elif short.triggered and short.confidence>=60:
                rr_s=(short.short_entry-short.short_target1)/(short.short_stop-short.short_entry+1e-8)
                final=f"🐻 [BEAR SHORT] 하락 추세 숏 (신뢰도 {short.confidence:.0f}%  손익비 1:{rr_s:.1f})"
            elif cb.triggered:
                final="🚨 [강제 HOLD] Circuit Breaker 발동 — 전략 없음"
            else:
                final="🛡️ [방어] 반등/숏 조건 미충족 — 현금 보유"

        # 공통 경고
        if mtf.success and not mtf.mtf_agree and "BUY" in final:
            final+="  ⚠️(MTF 상충)"
        if eng_a.cv_accuracy<50 and "BUY" in final:
            final+="  ⚠️(CV 낮음)"

        print(f"  ▶ 최종 판단: {final}")

        # 리스크 관리
        print(f"\n  📐 리스크 관리")
        if "BOUNCE" in final or ("BUY" in final and mode!="bull"):
            print(f"  반등 진입 : ${bounce.bounce_entry:,.2f}  손절 ${bounce.bounce_stop:,.2f}  1차익절 ${bounce.bounce_target1:,.2f}")
        elif "SHORT" in final:
            print(f"  숏 진입   : ${short.short_entry:,.2f}  손절 ${short.short_stop:,.2f}  1차익절 ${short.short_target1:,.2f}")
        else:
            cons_stop=max(eng_a.stop_price,eng_b.support_price,dyn_stop.recommended_stop if dyn_stop.success else 0)
            cons_tgt=min(eng_a.target_price,eng_b.resistance_price)
            rr=(cons_tgt-curr)/(curr-cons_stop) if cons_stop<curr else 0
            print(f"  권장 손절 : ${cons_stop:,.2f}  |  권장 익절 : ${cons_tgt:,.2f}  |  손익비 1:{rr:.1f}")

        # 켈리 비중 — [NEW 1] GARCH 동적 Kelly로 교체
        print(f"\n{'─'*W}")
        print(f"  📐 [GARCH KELLY] 동적 포지션 사이징")
        print(f"{'─'*W}")
        garch = GARCHKelly().run(df, eng_a.kelly_pct, macro.vix, beta)
        if garch.success:
            regime_emoji = {"low":"🟢","normal":"🟡","high":"🟠","extreme":"🔴"}.get(garch.vol_regime,"⚪")
            print(f"  예측 변동성  : 일간 {garch.vol_forecast:.2f}%  |  연환산 {garch.vol_annualized:.1f}%  {regime_emoji} {garch.vol_regime.upper()}")
            print(f"  변동성 백분위: {garch.vol_percentile:.0f}%ile  (과거 대비 {'높음' if garch.vol_percentile>70 else '낮음' if garch.vol_percentile<30 else '보통'})")
            print(f"  Kelly 원본   : {garch.kelly_raw:.1f}%")
            print(f"  Kelly GARCH  : {garch.kelly_garch:.1f}%  (스케일 ×{garch.scaling_factor:.2f})")
            print(f"  Kelly RP     : {garch.kelly_riskparity:.1f}%  (Risk Parity 기준)")
            print(f"  ▶ Kelly 최종 : {garch.kelly_final:.1f}%  ← 세 방법 중 가장 보수적 + 베타 보정({beta.ticker_type})")
        else:
            adjusted_kelly = round(eng_a.kelly_pct * beta.kelly_scale, 1)
            print(f"  켈리 비중 : {eng_a.kelly_pct:.1f}% × {beta.kelly_scale} ({beta.ticker_type}) = {adjusted_kelly:.1f}%")

    elif eng_a.success:
        print(f"  Engine A 단독 — {eng_a.direction}  확률: {eng_a.prob_up:.1f}%")
    elif eng_b.success:
        print(f"  Engine B 단독 — {eng_b.direction}  P50: ${eng_b.price_p50:,.2f}")
    else:
        print("  ❌ 두 엔진 모두 실패")

    print(f"{'━'*W}\n")

    # ── [NEW B] 신호 로그 저장 ────────────────────────────────
    if logger is not None and eng_a.success:
        # 최종 판단 문자열에서 신호 타입 추출
        try:
            sig_label = final.split("[")[1].split("]")[0] if "[" in final else "HOLD"
        except: sig_label = eng_a.direction

        if sig_label not in ("HOLD", "대기", "방어"):
            # 진입가 / 손절 / 익절
            if "BOUNCE" in sig_label and bounce.success:
                ep, sp, tp = bounce.bounce_entry, bounce.bounce_stop, bounce.bounce_target1
            elif "SHORT" in sig_label and short.success:
                ep, sp, tp = short.short_entry, short.short_stop, short.short_target1
            else:
                ep = curr
                sp = max(eng_a.stop_price, dyn_stop.recommended_stop) if dyn_stop.success else eng_a.stop_price
                tp = eng_a.target_price

            adj_kelly = garch.kelly_final if garch.success else round(eng_a.kelly_pct * beta.kelly_scale, 1)
            lid = logger.save(
                ticker=ticker, mode=mode, signal=sig_label,
                confidence=fused_conf if eng_b.success else eng_a.cv_accuracy,
                entry=ep, stop=sp, target=tp,
                kelly=adj_kelly, horizon=eng_a.optimal_days
            )
            print(f"  💾 신호 저장 완료 — Log ID #{lid}  ({LOG_FILE})")
            print(f"     {sig_label}  신뢰도 {fused_conf:.0f}%  진입 ${ep:,.2f}  손절 ${sp:,.2f}")
            print(f"     {eng_a.optimal_days}일 후 자동 검토 예정  |  python zeus_v17.py --review")
            print(f"{'━'*W}\n")


if __name__ == "__main__":
    args = sys.argv[1:]

    # ── --stats: 승률 통계만 출력 ──────────────────────────────
    if "--stats" in args:
        SignalLogger().stats()
        sys.exit(0)

    # ── --review: 과거 신호 결과 자동 업데이트 ────────────────
    if "--review" in args:
        SignalLogger().review()
        # review 후 stats도 바로 보여주기
        SignalLogger().stats()
        sys.exit(0)

    # ── 일반 분석 / 백테스트 ──────────────────────────────────
    run_bt = "--backtest" in args
    logger = SignalLogger()

    print("=" * 64)
    print("  ⚡ ZEUS ULTIMATE V18")
    print("  옵션: --backtest | --review | --stats")
    print("=" * 64)
    ticker = input("  티커: ").strip().upper()
    if not ticker:
        print("  ❌ 티커를 입력해주세요."); sys.exit(1)

    run_zeus_v17(ticker, run_backtest=run_bt, logger=logger)