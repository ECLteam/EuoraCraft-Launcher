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

  // --- Chart 1: Priority Distribution ---
  var chart1 = echarts.init(document.getElementById('chart-priority'), null, { renderer: 'svg' });
  chart1.setOption({
    tooltip: { trigger: 'axis', appendToBody: true, axisPointer: { type: 'shadow' } },
    animation: false,
    color: [accent5, accent4, accent3],
    legend: {
      data: ['P0 (立即)', 'P1 (短期)', 'P2 (长期)'],
      textStyle: { color: muted },
      bottom: 0
    },
    grid: { left: '3%', right: '4%', bottom: '16%', containLabel: true },
    xAxis: {
      type: 'category',
      data: ['后端', '前端', '基础设施'],
      axisLabel: { color: ink, fontSize: 12, fontWeight: 600 },
      axisLine: { lineStyle: { color: rule } }
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
        name: 'P0 (立即)',
        type: 'bar',
        stack: 'total',
        barWidth: '45%',
        data: [2, 4, 1],
        itemStyle: { color: accent5, borderRadius: [0, 0, 0, 0] }
      },
      {
        name: 'P1 (短期)',
        type: 'bar',
        stack: 'total',
        data: [6, 4, 5],
        itemStyle: { color: accent4 }
      },
      {
        name: 'P2 (长期)',
        type: 'bar',
        stack: 'total',
        data: [14, 10, 9],
        itemStyle: { color: accent3 }
      }
    ]
  });
  window.addEventListener('resize', function() { chart1.resize(); });

  // --- Chart 2: Layer Distribution ---
  var chart2 = echarts.init(document.getElementById('chart-layer'), null, { renderer: 'svg' });
  chart2.setOption({
    tooltip: {
      trigger: 'item',
      appendToBody: true,
      formatter: '{b}: {c} ({d}%)'
    },
    animation: false,
    color: [accent, accent2, accent3],
    series: [{
      type: 'pie',
      radius: ['35%', '65%'],
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
        formatter: '{b}\n({c} 项)'
      },
      emphasis: {
        label: { show: true, fontSize: 16, fontWeight: 'bold' }
      },
      data: [
        { value: 22, name: '后端 Python' },
        { value: 18, name: '前端 TS/Vue' },
        { value: 15, name: '基础设施' }
      ]
    }]
  });
  window.addEventListener('resize', function() { chart2.resize(); });
})();