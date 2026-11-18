/**
 * Jalali (Shamsi) Date Converter & Lightweight Date Picker for SoftEther Log Panel
 * 100% self-contained, zero external CDN dependencies.
 */

const Jalali = {
  gregorianToJalali(gy, gm, gd) {
    const g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
    let jy = (gy <= 1600) ? 0 : 979;
    gy -= (gy <= 1600) ? 621 : 1600;
    const gy2 = (gm > 2) ? (gy + 1) : gy;
    let days = (365 * gy) + parseInt((gy2 + 3) / 4) - parseInt((gy2 + 99) / 100) +
      parseInt((gy2 + 399) / 400) - 80 + gd + g_d_m[gm - 1];
    jy += 33 * parseInt(days / 12053);
    days %= 12053;
    jy += 4 * parseInt(days / 1461);
    days %= 1461;
    if (days > 365) {
      jy += parseInt((days - 1) / 365);
      days = (days - 1) % 365;
    }
    const jm = (days < 186) ? 1 + parseInt(days / 31) : 7 + parseInt((days - 186) / 30);
    const jd = 1 + ((days < 186) ? (days % 31) : ((days - 186) % 30));
    return [jy, jm, jd];
  },

  jalaliToGregorian(jy, jm, jd) {
    let gy = (jy <= 979) ? 621 : 1600;
    jy -= (jy <= 979) ? 0 : 979;
    let days = (365 * jy) + ((parseInt(jy / 33)) * 8) + parseInt(((jy % 33) + 3) / 4) +
      78 + jd + ((jm < 7) ? (jm - 1) * 31 : ((jm - 7) * 30) + 186);
    gy += 400 * parseInt(days / 146097);
    days %= 146097;
    if (days > 36524) {
      gy += 100 * parseInt(--days / 36524);
      days %= 36524;
      if (days >= 365) days++;
    }
    gy += 4 * parseInt(days / 1461);
    days %= 1461;
    if (days > 365) {
      gy += parseInt((days - 1) / 365);
      days = (days - 1) % 365;
    }
    let gd = days + 1;
    const sal_a = [0, 31, ((gy % 4 === 0 && gy % 100 !== 0) || (gy % 400 === 0)) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    let gm;
    for (gm = 0; gm < 13; gm++) {
      const v = sal_a[gm];
      if (gd <= v) break;
      gd -= v;
    }
    return [gy, gm, gd];
  },

  monthNamesFa: [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
  ],

  formatJalali(dateObj) {
    if (!dateObj) return "";
    const [jy, jm, jd] = this.gregorianToJalali(dateObj.getFullYear(), dateObj.getMonth() + 1, dateObj.getDate());
    const pad = (n) => (n < 10 ? '0' + n : n);
    return `${jy}/${pad(jm)}/${pad(jd)}`;
  },

  todayJalali() {
    return this.formatJalali(new Date());
  },

  getQuickRange(type) {
    const now = new Date();
    const pad = (n) => (n < 10 ? '0' + n : n);

    if (type === 'today') {
      const jToday = this.formatJalali(now);
      return { from: jToday, to: jToday };
    } else if (type === 'yesterday') {
      const y = new Date(now.getTime() - 24 * 3600 * 1000);
      const jYest = this.formatJalali(y);
      return { from: jYest, to: jYest };
    } else if (type === 'last7') {
      const past = new Date(now.getTime() - 7 * 24 * 3600 * 1000);
      return { from: this.formatJalali(past), to: this.formatJalali(now) };
    } else if (type === 'last30') {
      const past = new Date(now.getTime() - 30 * 24 * 3600 * 1000);
      return { from: this.formatJalali(past), to: this.formatJalali(now) };
    } else if (type === 'thisMonth') {
      const [jy, jm] = this.gregorianToJalali(now.getFullYear(), now.getMonth() + 1, now.getDate());
      return {
        from: `${jy}/${pad(jm)}/01`,
        to: this.formatJalali(now)
      };
    }
    return { from: "", to: "" };
  }
};
