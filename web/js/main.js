const tableBody = document.querySelector("#scheduleTable tbody");
let recommendedPalette = ["rgba(77, 171, 247, 0.75)", "rgba(51, 154, 240, 0.75)", "rgba(34, 139, 230, 0.75)"];
let currentTextColor = "#333333";
let currentGridColor = "rgba(0,0,0,0.1)";
let bgImage = null;

// 1. 색상 변환 및 분석 로직
function rgbToHsv(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
    let h, s = max === 0 ? 0 : d / max, v = max;
    if (max !== min) {
        if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
        else if (max === g) h = (b - r) / d + 2;
        else h = (r - g) / d + 4;
        h /= 6;
    }
    return [h, s, v];
}

function hsvToRgb(h, s, v) {
    let r, g, b, i = Math.floor(h * 6), f = h * 6 - i, p = v * (1 - s), q = v * (1 - f * s), t = v * (1 - (1 - f) * s);
    switch (i % 6) {
        case 0: r = v, g = t, b = p; break;
        case 1: r = q, g = v, b = p; break;
        case 2: r = p, g = v, b = t; break;
        case 3: r = p, g = q, b = v; break;
        case 4: r = t, g = p, b = v; break;
        case 5: r = v, g = p, b = q; break;
    }
    return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
}

async function analyzeImage(e) {
    const file = e.target.files[0];
    if (!file) return;

    bgImage = new Image();
    bgImage.src = URL.createObjectURL(file);
    await bgImage.decode();

    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    canvas.width = 100; canvas.height = 100;
    ctx.drawImage(bgImage, 0, 0, 100, 100);

    const pixels = ctx.getImageData(0, 0, 100, 100).data;
    let rSum = 0, gSum = 0, bSum = 0, count = 0;
    const colorCounts = {};

    for (let i = 0; i < pixels.length; i += 4) {
        const r = pixels[i], g = pixels[i+1], b = pixels[i+2];
        const brightness = (r + g + b) / 3;
        if (brightness > 30 && brightness < 225) {
            const key = `${r},${g},${b}`;
            colorCounts[key] = (colorCounts[key] || 0) + 1;
            rSum += r; gSum += g; bSum += b; count++;
        }
    }

    const sortedColors = Object.entries(colorCounts).sort((a, b) => b[1] - a[1]);
    const hues = sortedColors.map(c => rgbToHsv(...c[0].split(',').map(Number)))
                             .filter(hsv => hsv[1] >= 0.15).map(hsv => hsv[0]);

    const svPairs = [[0.60, 0.80], [0.70, 0.75], [0.55, 0.85], [0.65, 0.70], [0.75, 0.80]];
    recommendedPalette = hues.slice(0, 8).map((h, i) => {
        const [r, g, b] = hsvToRgb(h, svPairs[i % 5][0], svPairs[i % 5][1]);
        return `rgba(${r}, ${g}, ${b}, 0.75)`;
    });

    const avgB = (rSum + gSum + bSum) / (count * 3 || 1);
    currentTextColor = avgB < 128 ? "#FFFFFF" : "#1E1E1E";
    currentGridColor = avgB < 128 ? "rgba(255,255,255,0.15)" : "rgba(0,0,0,0.1)";

    document.getElementById('themeResultsInline').style.display = 'flex';
    updateThemeUI();
    renderAll();
}

function updateThemeUI() {
    const container = document.getElementById('paletteCircles');
    container.innerHTML = '';
    recommendedPalette.forEach(c => {
        const d = document.createElement('div'); d.className = 'color-circle'; d.style.background = c;
        container.appendChild(d);
    });
    document.getElementById('textSwatch').style.background = currentTextColor;
    document.getElementById('gridSwatch').style.background = currentGridColor;
}

// 2. 시간표 공통 그리기 로직 (플로팅 스타일 핵심)
function drawTimetable(ctx, width, height) {
    const TOP = 50, LEFT = 60, W = width - 80, H = height - 100;
    const dayW = W / 5, hourH = H / 13;
    const days = ["월", "화", "수", "목", "금"];

    // 요일 헤더
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.font = "bold 15px Jalnan2"; ctx.fillStyle = currentTextColor;
    days.forEach((d, i) => ctx.fillText(d, LEFT + i * dayW + dayW / 2, TOP - 25));

    // 그리드 및 시간 라벨
    ctx.strokeStyle = currentGridColor; ctx.lineWidth = 0.8;
    for (let i = 0; i <= 12; i++) {
        const y = TOP + i * hourH;
        ctx.beginPath(); ctx.moveTo(LEFT, y); ctx.lineTo(LEFT + W, y); ctx.stroke();
        ctx.font = "11px Jalnan2"; ctx.globalAlpha = 0.6;
        ctx.fillText(9 + i + ":00", LEFT - 30, y); ctx.globalAlpha = 1.0;
    }

    // 과목 데이터 렌더링
    const rows = document.querySelectorAll("#scheduleTable tbody tr");
    const subjectColors = {}; let colorIdx = 0;

    rows.forEach(row => {
        const name = row.querySelector(".name").value;
        if (!name) return;
        
        const day = days.indexOf(row.querySelector(".day").value);
        const sH = parseInt(row.querySelector(".sh").value), sM = parseInt(row.querySelector(".sm").value);
        const eH = parseInt(row.querySelector(".eh").value), eM = parseInt(row.querySelector(".em").value);
        const room = row.querySelector(".room").value;

        if (!subjectColors[name]) subjectColors[name] = recommendedPalette[colorIdx++ % recommendedPalette.length];

        const startY = TOP + (sH - 9 + sM/60) * hourH;
        const endY = TOP + (eH - 9 + eM/60) * hourH;
        const rectH = endY - startY;
        const centerX = LEFT + day * dayW + dayW / 2;
        const centerY = startY + rectH / 2;

        // 블록 그리기 (은은한 그림자 포함)
        ctx.save();
        ctx.shadowColor = "rgba(0,0,0,0.12)"; ctx.shadowBlur = 10;
        ctx.fillStyle = subjectColors[name];
        ctx.beginPath();
        ctx.roundRect(LEFT + day * dayW + 4, startY + 4, dayW - 8, rectH - 8, 12);
        ctx.fill();
        ctx.restore();

        // 텍스트 렌더링 (겹침 방지)
        ctx.fillStyle = currentTextColor;
        if (rectH > 45 && room) {
            ctx.font = "bold 11px Jalnan2"; ctx.fillText(name, centerX, centerY - 9);
            ctx.font = "9px Jalnan2"; ctx.globalAlpha = 0.85; ctx.fillText(room, centerX, centerY + 9);
            ctx.globalAlpha = 1.0;
        } else {
            ctx.font = "bold 10px Jalnan2"; ctx.fillText(name, centerX, centerY);
        }
    });
}

// 3. 메인 렌더링 관리
function renderAll() {
    renderPreview();
    if (bgImage) renderComposite();
}

function renderPreview() {
    const canvas = document.getElementById("timetableCanvas");
    const ctx = canvas.getContext("2d");
    canvas.width = 450; canvas.height = 650;
    ctx.fillStyle = "#FFFFFF"; ctx.fillRect(0, 0, 450, 650);
    drawTimetable(ctx, 450, 650);
}

function renderComposite() {
    const canvas = document.getElementById("compositeCanvas");
    const ctx = canvas.getContext("2d");
    canvas.width = bgImage.width; canvas.height = bgImage.height;
    
    // 배경 이미지
    ctx.drawImage(bgImage, 0, 0);

    // 시간표 우측 상단 배치
    const tableW = canvas.width * 0.42;
    const tableH = canvas.height * 0.88;
    const posX = canvas.width - tableW - 40;
    const posY = 40;

    ctx.save();
    ctx.translate(posX, posY);
    drawTimetable(ctx, tableW, tableH);
    ctx.restore();

    document.getElementById("compositePlaceholder").style.display = "none";
    document.getElementById("downloadBtn").style.display = "block";
}

// 4. 행 제어 및 초기화
function addRow(data = { day: "월", name: "", sh: "10", sm: "00", eh: "11", em: "30", room: "" }) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
        <td><select class="day">${["월","화","수","목","금"].map(d=>`<option ${data.day===d?'selected':''}>${d}</option>`).join('')}</select></td>
        <td><input type="text" class="name" value="${data.name}" placeholder="과목명"></td>
        <td><div class="time-group">
            <select class="sh">${Array.from({length:14},(_,i)=>`<option ${data.sh==String(i+9).padStart(2,'0')?'selected':''}>${String(i+9).padStart(2,'0')}</option>`).join('')}</select>:
            <select class="sm"><option ${data.sm=="00"?'selected':''}>00</option><option ${data.sm=="30"?'selected':''}>30</option></select> ~
            <select class="eh">${Array.from({length:14},(_,i)=>`<option ${data.eh==String(i+9).padStart(2,'0')?'selected':''}>${String(i+9).padStart(2,'0')}</option>`).join('')}</select>:
            <select class="em"><option ${data.em=="00"?'selected':''}>00</option><option ${data.em=="30"?'selected':''}>30</option></select>
        </div></td>
        <td><input type="text" class="room" value="${data.room}" placeholder="강의실"></td>
        <td><button onclick="this.parentElement.parentElement.remove(); renderAll();" style="border:none; background:none; color:#ff6b6b; cursor:pointer; font-size:1.2rem;">✕</button></td>
    `;
    tableBody.appendChild(tr);
}

function downloadComposite() {
    const link = document.createElement('a');
    link.download = `timetable_composite_${new Date().getTime()}.png`;
    link.href = document.getElementById('compositeCanvas').toDataURL("image/png");
    link.click();
}

window.onload = () => {
    addRow({day:"월", name:"전공 수업", sh:"10", sm:"30", eh:"12", em:"00", room:"공학관 302호"});
    renderPreview();
};