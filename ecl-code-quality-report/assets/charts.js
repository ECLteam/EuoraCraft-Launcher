(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var accent3 = style.getPropertyValue('--accent3').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  // --- Chart 1: 代码总览分布 (Pie) ---
  var chart1 = echarts.init(document.getElementById('chart-overview'), null, { renderer: 'svg' });
  chart1.setOption({
    tooltip: { trigger: 'item', appendToBody: true, formatter: '{b}: {c} 行 ({d}%)' },
    animation: false,
    color: [accent, accent2, accent3, '#ffc800', '#6c5ce7'],
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['50%', '50%'],
      avoidLabelOverlap: true,
      padAngle: 2,
      itemStyle: { borderRadius: 6, borderColor: 'var(--bg)', borderWidth: 2 },
      label: { show: true, formatter: '{b}\n{c} 行', color: ink, fontSize: 11 },
      emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
      data: [
        { value: 18916, name: 'Python 后端' },
        { value: 12978, name: 'TypeScript' },
        { value: 8798, name: 'Vue 组件' },
        { value: 7631, name: 'CSS 样式' },
        { value: 1500, name: '其他' }
      ]
    }]
  });
  window.addEventListener('resize', function() { chart1.resize(); });

  // --- Chart 2: 各维度评分 (Radar) ---
  var chart2 = echarts.init(document.getElementById('chart-radar'), null, { renderer: 'svg' });
  chart2.setOption({
    tooltip: { appendToBody: true },
    animation: false,
    color: [accent],
    radar: {
      indicator: [
        { name: 'TypeScript 安全', max: 10 },
        { name: '架构设计', max: 10 },
        { name: '测试质量', max: 10 },
        { name: '后端代码', max: 10 },
        { name: '前端代码', max: 10 },
        { name: 'CI/CD 完整度', max: 10 },
        { name: '国际化', max: 10 },
        { name: '样式组织', max: 10 }
      ],
      shape: 'circle',
      splitNumber: 5,
      axisName: { color: muted, fontSize: 10 },
      splitLine: { lineStyle: { color: rule } },
      splitArea: { areaStyle: { color: [bg2 + '55', bg2 + '33'] } },
      axisLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'radar',
      data: [{ value: [9, 9, 8, 7.5, 7.5, 6, 10, 9], name: '项目评分' }],
      areaStyle: { color: accent + '33' },
      lineStyle: { color: accent, width: 2 },
      itemStyle: { color: accent2 }
    }]
  });
  window.addEventListener('resize', function() { chart2.resize(); });

  // --- Chart 3: Python 文件分布 (Bar) ---
  var chart3 = echarts.init(document.getElementById('chart-file-sizes'), null, { renderer: 'svg' });
  chart3.setOption({
    tooltip: { trigger: 'axis', appendToBody: true, axisPointer: { type: 'shadow' } },
    animation: false,
    grid: { left: 180, right: 30, top: 20, bottom: 30 },
    xAxis: { type: 'value', axisLabel: { color: muted }, splitLine: { lineStyle: { color: rule } } },
    yAxis: {
      type: 'category',
      data: ['accounts.py', 'MicrosoftAuth.py', 'Downloader.py', 'plugin.py', 'YggdrasilAuth.py', 'ECLauncherCore.py', 'tauri.py', 'NetLibs.py', 'files.py', 'bridge.py', 'JavaScanner.py'],
      axisLabel: { color: ink, fontSize: 10, fontFamily: 'JetBrainsMono, monospace' },
      splitLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'bar',
      data: [
        { value: 821, itemStyle: { color: accent3 } },
        { value: 526, itemStyle: { color: accent3 } },
        { value: 479, itemStyle: { color: accent3 } },
        { value: 467, itemStyle: { color: accent3 } },
        { value: 425, itemStyle: { color: accent3 } },
        { value: 423, itemStyle: { color: accent3 } },
        { value: 363, itemStyle: { color: accent } },
        { value: 363, itemStyle: { color: accent } },
        { value: 353, itemStyle: { color: accent } },
        { value: 344, itemStyle: { color: accent } },
        { value: 325, itemStyle: { color: accent } }
      ],
      barWidth: 14,
      label: { show: true, position: 'right', color: muted, fontSize: 10, formatter: '{c} 行' }
    }]
  });
  window.addEventListener('resize', function() { chart3.resize(); });

  // --- Chart 4: 测试覆盖分布 (Bar) ---
  var chart4 = echarts.init(document.getElementById('chart-test-coverage'), null, { renderer: 'svg' });
  chart4.setOption({
    tooltip: { trigger: 'axis', appendToBody: true, axisPointer: { type: 'shadow' } },
    animation: false,
    grid: { left: 160, right: 30, top: 20, bottom: 30 },
    xAxis: { type: 'value', axisLabel: { color: muted }, splitLine: { lineStyle: { color: rule } } },
    yAxis: {
      type: 'category',
      data: ['accounts', 'game', 'plugins', 'authlib', 'frontend', 'wardrobe', 'config', 'event_bus', 'game/Core'],
      axisLabel: { color: ink, fontSize: 10, fontFamily: 'JetBrainsMono, monospace' },
      splitLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'bar',
      data: [
        { value: 27, itemStyle: { color: accent2 } },
        { value: 29, itemStyle: { color: accent2 } },
        { value: 37, itemStyle: { color: accent2 } },
        { value: 10, itemStyle: { color: accent2 } },
        { value: 32, itemStyle: { color: accent2 } },
        { value: 6, itemStyle: { color: accent } },
        { value: 6, itemStyle: { color: accent } },
        { value: 3, itemStyle: { color: '#ffc800' } },
        { value: 0, itemStyle: { color: accent3 } }
      ],
      barWidth: 14,
      label: { show: true, position: 'right', color: muted, fontSize: 10, formatter: '{c} 用例' }
    }]
  });
  window.addEventListener('resize', function() { chart4.resize(); });

  // --- Chart 5: 前端组件规模 (Bar) ---
  var chart5 = echarts.init(document.getElementById('chart-component-sizes'), null, { renderer: 'svg' });
  chart5.setOption({
    tooltip: { trigger: 'axis', appendToBody: true, axisPointer: { type: 'shadow' } },
    animation: false,
    grid: { left: 220, right: 30, top: 20, bottom: 30 },
    xAxis: { type: 'value', axisLabel: { color: muted }, splitLine: { lineStyle: { color: rule } }, max: 700 },
    yAxis: {
      type: 'category',
      data: ['InstanceDetailModal', 'Game.vue', 'WardrobeModal', 'ManageTab', 'InstancesTab', 'OnlineModSearch', 'GameLaunchBar', 'SideBar', 'GameTab'],
      axisLabel: { color: ink, fontSize: 10, fontFamily: 'JetBrainsMono, monospace' },
      splitLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'bar',
      data: [
        { value: 617, itemStyle: { color: accent3 } },
        { value: 557, itemStyle: { color: accent3 } },
        { value: 518, itemStyle: { color: accent } },
        { value: 514, itemStyle: { color: accent } },
        { value: 497, itemStyle: { color: accent } },
        { value: 371, itemStyle: { color: accent } },
        { value: 350, itemStyle: { color: accent } },
        { value: 337, itemStyle: { color: accent } },
        { value: 311, itemStyle: { color: '#ffc800' } }
      ],
      barWidth: 14,
      label: { show: true, position: 'right', color: muted, fontSize: 10, formatter: '{c} 行' }
    }]
  });
  window.addEventListener('resize', function() { chart5.resize(); });
})();