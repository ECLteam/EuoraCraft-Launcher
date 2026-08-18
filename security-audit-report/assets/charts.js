(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var accent3 = style.getPropertyValue('--accent3').trim();
  var accent4 = style.getPropertyValue('--accent4').trim();
  var accent5 = style.getPropertyValue('--accent5').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var bg3 = style.getPropertyValue('--bg3').trim();

  // --- Chart 1: Severity Distribution ---
  var chart1 = echarts.init(document.getElementById('chart-severity'), null, { renderer: 'svg' });
  chart1.setOption({
    tooltip: {
      trigger: 'item',
      appendToBody: true,
      formatter: '{b}: {c} ({d}%)'
    },
    animation: false,
    color: [accent, accent2, accent3, accent4],
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['50%', '50%'],
      avoidLabelOverlap: true,
      itemStyle: {
        borderRadius: 6,
        borderColor: bg2,
        borderWidth: 2
      },
      label: {
        show: true,
        color: ink,
        fontSize: 13,
        fontWeight: 600,
        formatter: '{b}\n{c}'
      },
      emphasis: {
        label: { show: true, fontSize: 16, fontWeight: 'bold' }
      },
      data: [
        { value: 0, name: '严重' },
        { value: 6, name: '高危' },
        { value: 12, name: '中危' },
        { value: 14, name: '低危' }
      ]
    }]
  });
  window.addEventListener('resize', function() { chart1.resize(); });

  // --- Chart 2: Category Distribution ---
  var chart2 = echarts.init(document.getElementById('chart-category'), null, { renderer: 'svg' });
  chart2.setOption({
    tooltip: {
      trigger: 'axis',
      appendToBody: true,
      axisPointer: { type: 'shadow' }
    },
    animation: false,
    color: [accent, accent2, accent3, accent5],
    legend: {
      data: ['高危', '中危', '低危'],
      textStyle: { color: muted },
      bottom: 0
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: ['安全漏洞', '逻辑缺陷', '隐藏问题', '配置与基础设施'],
      axisLabel: { color: ink, fontSize: 12 },
      axisLine: { lineStyle: { color: rule } },
      axisTick: { alignWithLabel: true }
    },
    yAxis: {
      type: 'value',
      name: '问题数量',
      nameTextStyle: { color: muted },
      axisLabel: { color: muted },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } }
    },
    series: [
      {
        name: '高危',
        type: 'bar',
        stack: 'total',
        barWidth: '50%',
        data: [4, 0, 0, 2],
        itemStyle: { color: accent2 }
      },
      {
        name: '中危',
        type: 'bar',
        stack: 'total',
        data: [3, 2, 2, 5],
        itemStyle: { color: accent3 }
      },
      {
        name: '低危',
        type: 'bar',
        stack: 'total',
        data: [1, 4, 8, 1],
        itemStyle: { color: accent4 }
      }
    ]
  });
  window.addEventListener('resize', function() { chart2.resize(); });
})();