/**
 * 上传速度追踪器。
 *
 * 记录任务从开始到当前的上传速度采样，计算瞬时速度，并为面板中的
 * 速度曲线提供数据。采样点包含暂停期间的速度 0，因此曲线能完整
 * 反映任务的活跃与暂停阶段。
 */

/** 采样间隔（毫秒）。 */
const SAMPLE_INTERVAL_MILLISECONDS = 500;

/** 采样点上限；超出后隔点抽稀，保留从任务开始到当前的走势。 */
const MAX_SAMPLE_COUNT = 600;

/** 瞬时速度的指数平滑系数。 */
const SMOOTHING_FACTOR = 0.35;

export class SpeedTracker {
  /**
   * @param {number} totalBytes 任务总字节数。
   */
  constructor(totalBytes) {
    this.totalBytes = Math.max(0, Number(totalBytes) || 0);
    this.startedAt = null;
    this.activeStartedAt = null;
    this.activeMilliseconds = 0;
    this.samples = [];
    this.lastSampleTime = null;
    this.lastSampleBytes = 0;
    this.currentInstantSpeed = 0;
  }

  /**
   * 开始或恢复计时。
   */
  resume() {
    const now = Date.now();
    if (this.startedAt === null) {
      this.startedAt = now;
      this.samples.push({ seconds: 0, speed: 0 });
    }
    if (this.activeStartedAt === null) {
      this.activeStartedAt = now;
      this.lastSampleTime = now;
      this.currentInstantSpeed = 0;
    }
  }

  /**
   * 暂停计时，并记录一个速度为 0 的采样点。
   */
  pause() {
    const now = Date.now();
    if (this.activeStartedAt !== null) {
      this.activeMilliseconds += now - this.activeStartedAt;
      this.activeStartedAt = null;
    }
    this.currentInstantSpeed = 0;
    this.recordSample(now, 0);
    this.lastSampleTime = now;
  }

  /**
   * 将采样基准重置到当前进度。
   *
   * 暂停后继续时，已中止的小文件会从 0 重新发送，需要重置基准，
   * 避免速度长时间显示为 0。
   *
   * @param {number} uploadedBytes 当前已上传字节数。
   */
  resetProgress(uploadedBytes) {
    this.lastSampleBytes = Math.max(0, Number(uploadedBytes) || 0);
    this.currentInstantSpeed = 0;
    this.lastSampleTime = Date.now();
  }

  /**
   * 记录一次上传进度并更新瞬时速度。
   *
   * @param {number} uploadedBytes 当前已上传字节数。
   */
  sample(uploadedBytes) {
    const bytes = Math.max(0, Number(uploadedBytes) || 0);
    const previousBytes = this.lastSampleBytes;
    this.lastSampleBytes = bytes;
    if (this.activeStartedAt === null) {
      return;
    }

    const now = Date.now();
    if (this.lastSampleTime === null) {
      this.lastSampleTime = now;
      return;
    }
    const elapsedMilliseconds = now - this.lastSampleTime;
    if (elapsedMilliseconds < SAMPLE_INTERVAL_MILLISECONDS) {
      return;
    }

    const deltaBytes = Math.max(0, bytes - previousBytes);
    const rawSpeed = deltaBytes / (elapsedMilliseconds / 1000);
    this.currentInstantSpeed =
      this.currentInstantSpeed === 0
        ? rawSpeed
        : this.currentInstantSpeed * (1 - SMOOTHING_FACTOR) +
          rawSpeed * SMOOTHING_FACTOR;
    this.lastSampleTime = now;
    this.recordSample(now, this.currentInstantSpeed);
  }

  /**
   * 记录采样点，必要时抽稀历史数据。
   *
   * @param {number} now 当前毫秒时间戳。
   * @param {number} speed 当前速度（字节/秒）。
   */
  recordSample(now, speed) {
    if (this.startedAt === null) {
      return;
    }
    this.samples.push({
      seconds: Math.max(0, (now - this.startedAt) / 1000),
      speed: Math.max(0, speed),
    });
    if (this.samples.length > MAX_SAMPLE_COUNT) {
      this.samples = this.samples.filter(
        (sample, index) => index % 2 === 0
      );
    }
  }

  /**
   * 计算活跃计时秒数，不含暂停时间。
   *
   * @param {number} [now] 当前毫秒时间戳。
   * @returns {number} 活跃秒数。
   */
  getElapsedSeconds(now = Date.now()) {
    let milliseconds = this.activeMilliseconds;
    if (this.activeStartedAt !== null) {
      milliseconds += now - this.activeStartedAt;
    }
    return milliseconds / 1000;
  }

  /**
   * 返回当前瞬时速度。
   *
   * @returns {number} 字节/秒。
   */
  getInstantaneousSpeed() {
    return this.activeStartedAt === null ? 0 : this.currentInstantSpeed;
  }

  /**
   * 返回速度采样点列表。
   *
   * @returns {Array<{seconds: number, speed: number}>} 采样点。
   */
  getSamples() {
    return this.samples;
  }
}
