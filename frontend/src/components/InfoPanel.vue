<script setup>
const props = defineProps({
  path: { type: Array, required: true },
  totalNodes: { type: Number, required: true },
  totalEdges: { type: Number, required: true },
  currentNeighborCount: { type: Number, default: 0 },
})

function reload() {
  window.location.reload()
}
</script>

<template>
  <aside class="panel">
    <div class="panel-header">
      <h1>گراف شش‌لایه‌ی دایره‌ای</h1>
      <p class="subtitle">۴۸ تیم &middot; ۴۷۳ نود &middot; ۷۸۰ یال</p>
    </div>

    <div class="stat-row">
      <div class="stat">
        <span class="stat-value">{{ totalNodes }}</span>
        <span class="stat-label">نود</span>
      </div>
      <div class="stat">
        <span class="stat-value">{{ totalEdges }}</span>
        <span class="stat-label">یال</span>
      </div>
      <div class="stat">
        <span class="stat-value">{{ path.length }}</span>
        <span class="stat-label">نود انتخاب‌شده</span>
      </div>
    </div>

    <div class="instructions" v-if="path.length === 0">
      <p>
        برای شروع، یکی از نودهای <strong>لوزی زرد</strong> حلقه‌ی بیرونی
        (فقط آن‌هایی که فلش رو به بیرون دارند) را انتخاب کنید.
      </p>
    </div>
    <div class="instructions" v-else>
      <p>
        مسیر شما یک <strong>مولفه</strong> است. از هر نود انتخاب‌شده می‌توانید
        همسایه‌هایش را به مولفه اضافه کنید.
      </p>
      <p class="hint">تعداد همسایه‌های قابل‌انتخاب فعلی: {{ currentNeighborCount }}</p>
    </div>

    <div class="path-trace" v-if="path.length > 0">
      <h2>مولفه‌ی انتخاب‌شده</h2>
      <ol>
        <li v-for="(id, i) in path" :key="i" :class="{ last: i === path.length - 1 }">
          {{ id }}
        </li>
      </ol>
    </div>

    <button class="reset-btn" @click="reload">
      ↻ شروع دوباره (رفرش صفحه)
    </button>

    <div class="legend">
      <h2>راهنمای رنگ‌ها</h2>
      <div class="legend-item"><span class="dot diamond" style="background:#f2c200"></span> زرد لوزی — نقطه شروع</div>
      <div class="legend-item"><span class="dot square" style="background:#17becf"></span> فیروزه‌ای — دروازه ورود به لایه داخلی</div>
      <div class="legend-item"><span class="dot" style="background:#1f77b4"></span> آبی — لایه ۱</div>
      <div class="legend-item"><span class="dot" style="background:#ff7f0e"></span> نارنجی — لایه ۲</div>
      <div class="legend-item"><span class="dot" style="background:#2ca02c"></span> سبز — لایه ۳</div>
      <div class="legend-item"><span class="dot" style="background:#e377c2"></span> صورتی — اتصال لایه‌های ۳ و ۴</div>
      <div class="legend-item"><span class="dot" style="background:#d62728"></span> قرمز — لایه ۴</div>
      <div class="legend-item"><span class="dot square" style="background:#7f7f7f"></span> خاکستری — اتصال لایه‌های ۴ و ۵</div>
      <div class="legend-item"><span class="dot" style="background:#9467bd"></span> بنفش — لایه ۵</div>
      <div class="legend-item"><span class="dot" style="background:#8c564b"></span> قهوه‌ای — لایه ۶</div>
      <div class="legend-item"><span class="dot" style="background:#1f4e79"></span> آبی تیره — مرکز</div>
    </div>
  </aside>
</template>

<style scoped>
.panel {
  width: 320px;
  min-width: 320px;
  height: 100%;
  overflow-y: auto;
  background: #ffffff;
  border-left: 1px solid #e6e9ee;
  padding: 24px 20px;
  box-sizing: border-box;
  font-family: var(--font-primary);
  direction: rtl;
}

.panel-header h1 {
  font-size: 18px;
  margin: 0 0 4px;
  color: #1a1a1a;
}
.subtitle {
  margin: 0 0 20px;
  color: #888;
  font-size: 13px;
}

.stat-row {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}
.stat {
  flex: 1;
  background: #f6f8fb;
  border-radius: 10px;
  padding: 10px 6px;
  text-align: center;
}
.stat-value {
  display: block;
  font-size: 20px;
  font-weight: 700;
  color: #2b6ca8;
}
.stat-label {
  display: block;
  font-size: 11px;
  color: #888;
  margin-top: 2px;
}

.instructions {
  background: #f0f6fb;
  border: 1px solid #d7e8f5;
  border-radius: 10px;
  padding: 12px 14px;
  font-size: 13.5px;
  line-height: 1.9;
  color: #333;
  margin-bottom: 18px;
}
.instructions .hint {
  margin: 6px 0 0;
  color: #2b6ca8;
  font-weight: 600;
}

.path-trace {
  margin-bottom: 18px;
}
.path-trace h2,
.legend h2 {
  font-size: 13px;
  color: #555;
  margin: 0 0 8px;
  font-weight: 700;
}
.path-trace ol {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 180px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.path-trace li {
  background: #f6f8fb;
  border-radius: 6px;
  padding: 5px 10px;
  font-size: 12.5px;
  font-family: monospace;
  color: #555;
}
.path-trace li.last {
  background: #2b6ca8;
  color: #fff;
  font-weight: 700;
}

.reset-btn {
  width: 100%;
  padding: 11px;
  border: none;
  border-radius: 10px;
  background: #1a1a1a;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  margin-bottom: 22px;
  transition: background 0.2s ease;
}
.reset-btn:hover {
  background: #333;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  color: #444;
  margin-bottom: 6px;
}
.dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 1px solid rgba(0,0,0,0.3);
  flex-shrink: 0;
}
.dot.square {
  border-radius: 3px;
}
.dot.diamond {
  border-radius: 2px;
  transform: rotate(45deg);
}
</style>
