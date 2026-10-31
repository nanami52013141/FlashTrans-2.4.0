// 拖拽窗口时的性能优化。
//
// FlashTrans 的窗口是「无边框 + 透明 + 亚克力 + 阴影」的自定义外观，移动时整窗每帧
// 都要重绘/重新合成，在集显或老机器上会明显卡顿。这里在拖拽开始/结束时临时给 <body>
// 加一个 .dragging 类，由 CSS（见 theme.css）关掉 box-shadow / transition / animation /
// backdrop-filter / filter 这些重绘开销大的属性，松手后自动恢复 —— 外观不变，拖动变顺。
export function installDragPerf(): void {
  let dragging = false;

  const setDragging = (on: boolean) => {
    if (on === dragging) return;
    dragging = on;
    document.body.classList.toggle("dragging", on);
  };

  const attach = () => {
    const onDown = (e: Event) => {
      const el = e.target as HTMLElement | null;
      if (!el || !el.closest) return;
      // 标题栏里的按钮 / 输入框 / 链接不应进入“拖拽态”
      if (el.closest("button, input, select, textarea, a")) return;
      if (!el.closest("[data-tauri-drag-region]")) return;
      setDragging(true);
    };
    const onUp = () => setDragging(false);

    window.addEventListener("mousedown", onDown, true);
    window.addEventListener("mouseup", onUp, true);
    window.addEventListener("blur", onUp);
    document.addEventListener("mouseleave", onUp);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", attach);
  } else {
    attach();
  }
}
