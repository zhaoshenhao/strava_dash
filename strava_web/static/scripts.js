/**
 * 将距离从米转换为公里或英里。
 * @param {number} distance - 距离，单位米。默认为 0。
 * @param {boolean} use_metric - 是否使用公制单位（公里）。默认为 true。
 * @returns {string} 格式化后的距离字符串（保留两位小数，带单位）。
 */
function convertDistance(distance = 0, use_metric = true) {
    if (use_metric) {
        // 转换为公里
        return (distance / 1000).toFixed(2);
    } else {
        // 转换为英里 (1 米 ≈ 0.000621371 英里)
        return (distance * 0.000621371).toFixed(2);
    }
}

/**
 * 将秒数转换为格式化的持续时间字符串。
 * @param {number} seconds - 持续时间，单位秒。默认为 0。
 * @param {number} format - 格式类型 (1: d HH:MM:SS, 2: HH:MM:SS, 3: MM:SS)。默认为 1。
 * @returns {string} 格式化后的持续时间字符串。
 */
function formatDuration(seconds = 0, format = 1) {
    if (seconds <= 0) {
        if (format === 3) {
            return "--:--"
        } else {
            return "--:--:--"
        }
    }
            
    seconds = Math.max(0, Math.round(seconds)); // 确保非负整数

    const days = Math.floor(seconds / (24 * 3600));
    seconds %= (24 * 3600);
    const hours = Math.floor(seconds / 3600);
    seconds %= 3600;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;

    const pad = (num) => String(num).padStart(2, '0');

    if (format === 3) {
        return `${pad(minutes)}:${pad(remainingSeconds)}`;
    } else if (format === 2) {
        return `${pad(hours)}:${pad(minutes)}:${pad(remainingSeconds)}`;
    } else { // format === 1
        if (days > 0) {
            return `${days}d ${pad(hours)}:${pad(minutes)}:${pad(remainingSeconds)}`;
        } else {
            return `${pad(hours)}:${pad(minutes)}:${pad(remainingSeconds)}`;
        }
    }
}

/**
 * 将 HH:MM:SS 或 MM:SS 格式的字符串转换为总秒数。
 * 允许 HH 超过 99。如果格式无效或为负值，则返回 0。
 *
 * @param {string} hmsString - 时间字符串，例如 "01:05:30", "5:30", "1:00:00", "120:00:00"。
 * @returns {number} 总秒数。如果格式无效或为负值，则返回 0。
 */
function hmsToSeconds(hmsString) {
    if (typeof hmsString !== 'string') {
        return 0;
    }
    hmsString = hmsString.trim();
    if (hmsString === '') {
        return 0;
    }

    const parts = hmsString.split(':');
    let totalSeconds = 0;
    let isValid = true;

    if (parts.length === 3) {
        // HH:MM:SS
        const hours = parseInt(parts[0], 10);
        const minutes = parseInt(parts[1], 10);
        const seconds = parseInt(parts[2], 10);

        if (isNaN(hours) || isNaN(minutes) || isNaN(seconds) ||
            hours < 0 || minutes < 0 || seconds < 0 ||
            minutes >= 60 || seconds >= 60) {
            isValid = false;
        } else {
            totalSeconds = hours * 3600 + minutes * 60 + seconds;
        }
    } else if (parts.length === 2) {
        // MM:SS
        const minutes = parseInt(parts[0], 10);
        const seconds = parseInt(parts[1], 10);

        if (isNaN(minutes) || isNaN(seconds) ||
            minutes < 0 || seconds < 0 ||
            seconds >= 60) {
            isValid = false;
        } else {
            totalSeconds = minutes * 60 + seconds;
        }
    } else {
        isValid = false; // 无法识别的格式
    }

    if (!isValid) {
        return 0; // 无效输入返回 0
    }

    return Math.max(0, totalSeconds); // 确保返回非负秒数
}

/**
 * 将海拔提升从米转换为米或英尺。
 * @param {number} gain - 海拔提升，单位米。默认为 0。
 * @param {boolean} use_metric - 是否使用公制单位（米）。默认为 true。
 * @returns {string} 格式化后的海拔提升字符串（带单位）。
 */
function convertElevationGain(gain = 0, use_metric = true) {
    if (use_metric) {
        // 保持米
        return gain.toFixed(2) + ' m';
    } else {
        // 转换为英尺 (1 米 ≈ 3.28084 英尺)
        return (gain * 3.28084).toFixed(2) + ' ft';
    }
}

/**
 * 将速度（米/秒）转换为跑步配速（每公里或每英里）。
 * @param {number} speed - 速度，单位米/秒。默认为 0。
 * @param {boolean} use_metric - 是否使用公制配速（每公里）。默认为 true。
 * @returns {string} 格式化后的配速字符串 (HH:MM:SS 或 MM:SS)。如果 speed 为 0，返回 "--:--:--"。
 */
function convertSpeedToPace(speed = 0, use_metric = true) {
    if (speed === 0) {
        return "--:--:--"; // 或者你希望的默认值，例如 "00:00:00"
    }

    let secondsPerUnit; // 每单位距离所需的秒数

    if (use_metric) {
        // 每公里配速 (秒/米 * 1000 米/公里)
        secondsPerUnit = 1000 / speed;
    } else {
        // 每英里配速 (秒/米 * 1609.34 米/英里)
        secondsPerUnit = 1609.34 / speed;
    }

    secondsPerUnit = Math.round(secondsPerUnit); // 四舍五入到最近的整数秒

    const hours = Math.floor(secondsPerUnit / 3600);
    const minutes = Math.floor((secondsPerUnit % 3600) / 60);
    const seconds = secondsPerUnit % 60;

    const pad = (num) => String(num).padStart(2, '0');

    if (hours > 0) {
        return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
    } else {
        return `${pad(minutes)}:${pad(seconds)}`;
    }
}

/**
 * 将踏频 cadence 转换为步频 (cadence * 2)。
 * @param {number} cadence - 踏频。
 * @returns {number} 步频。
 */
function convertCadenceToSteps(cadence) {
    // 假设 cadence 已经是每分钟的单腿踏频，步频是双腿。
    // 如果 cadence 是每分钟的双腿步频，那就不需要乘以2。这里按照你的要求直接乘以2。
    return cadence * 2;
}

/**
 * 将数字格式化为带有千位分隔符的字符串，并保留指定的小数位数。
 * 例如：10000000.00 -> "10,000,000.00"
 * @param {number} number - 要格式化的数字。
 * @param {number} decimalPlaces - 小数点后保留的位数。默认为 2。
 * @returns {string} 格式化后的数字字符串。如果输入无效，返回 "Invalid Number"。
 */
function formatNumberWithCommas(number, decimalPlaces = 2) {
    if (typeof number !== 'number' || isNaN(number)) {
        return 'Invalid Number'; // 处理非数字输入
    }

    // 将数字四舍五入并转换为固定小数位数的字符串
    const fixedNumber = number.toFixed(decimalPlaces);

    // 分离整数部分和小数部分
    let [integerPart, decimalPart] = fixedNumber.split('.');

    // 对整数部分添加千位分隔符
    const formattedIntegerPart = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',');

    // 组合结果
    if (decimalPlaces > 0) {
        return `${formattedIntegerPart}.${decimalPart}`;
    } else {
        return formattedIntegerPart;
    }
}

function showToast(message, type) {
    const toastContainer = document.querySelector('.toast-container'); // 选择 base.html 中的 Toast 容器
    if (!toastContainer) {
        console.warn("Toast container not found. Message won't be displayed:", message);
        return;
    }
    const toastHtml = `
        <div class="toast align-items-center text-white bg-${type} border-0" role="alert" aria-live="assertive" aria-atomic="true" data-bs-autohide="true" data-bs-delay="15000">
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>`;
    const div = document.createElement('div');
    div.innerHTML = toastHtml;
    const newToastEl = div.firstElementChild;
    toastContainer.appendChild(newToastEl);
    const newToast = new bootstrap.Toast(newToastEl, { autohide: true, delay: 5000 });
    newToast.show();
    
    newToastEl.addEventListener('hidden.bs.toast', function () {
        newToastEl.remove();
    });
}

