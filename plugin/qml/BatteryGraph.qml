import QtQuick
import qs.Commons
import qs.Widgets

Item {
  id: root

  property var graph: ({})
  property var estimate: ({})
  property color accentColor: Color.mPrimary
  property real latestAtMs: NaN
  property string emptyLabel: "No history yet"
  property string sparseLabel: "Need more samples"
  property int minimumRenderablePoints: 3

  readonly property real surfaceHeight: Math.round(78 * Style.uiScaleRatio)
  readonly property var rawPoints: sortedGraphPoints(graph)
  readonly property real estimateWindowMs: resolvedEstimateWindowMs()
  readonly property bool hasProjection: projectionAvailable()
  readonly property int pointCount: rawPoints.length
  readonly property var graphSegments: buildGraphSegments(rawPoints)
  readonly property int longestSegmentLength: maxGraphSegmentLength(graphSegments)
  readonly property real projectionEndMs: projectedEndTimestampMs()
  readonly property real projectionWindowStartMs: projectedWindowStartTimestampMs()
  readonly property real resolvedEndMs: endTimestampMs()
  readonly property real resolvedStartMs: startTimestampMs()
  readonly property real resolvedSpanMs: Math.max(1, resolvedEndMs - resolvedStartMs)
  readonly property bool canRenderGraph: longestSegmentLength >= minimumRenderablePoints
  readonly property real resolvedMinValue: renderMinValue()
  readonly property real resolvedMaxValue: renderMaxValue()

  implicitHeight: graphSurface.height + (canRenderGraph ? labelRow.height + Style.marginXS : 0)

  function numericValue(value, fallback) {
    const numeric = Number(value);
    return isFinite(numeric) ? numeric : fallback;
  }

  function pointTimeMs(point) {
    return numericValue(point ? point.t : NaN, 0) * 1000;
  }

  function sortedGraphPoints(graphValue) {
    const rawPoints = graphValue && graphValue.points && graphValue.points.slice ? graphValue.points.slice() : [];
    const points = [];
    for (let i = 0; i < rawPoints.length; ++i) {
      const point = rawPoints[i];
      const timestamp = Number(point ? point.t : NaN);
      const value = Number(point ? point.value : NaN);
      if (isFinite(timestamp) && isFinite(value))
        points.push({ t: timestamp, value: value, breakBefore: point && point.break_before === true });
    }
    points.sort(function(a, b) { return a.t - b.t; });
    return points;
  }

  function buildGraphSegments(points) {
    const segments = [];
    let current = [];
    for (let i = 0; i < points.length; ++i) {
      const point = points[i];
      if (point.breakBefore && current.length > 0) {
        segments.push(current);
        current = [];
      }
      current.push(point);
    }
    if (current.length > 0)
      segments.push(current);
    return segments;
  }

  function maxGraphSegmentLength(segments) {
    let maxLength = 0;
    for (let i = 0; i < segments.length; ++i)
      maxLength = Math.max(maxLength, segments[i].length);
    return maxLength;
  }

  function endTimestampMs() {
    if (hasProjection)
      return Math.max(projectionEndMs, latestPointMs());
    const explicitLatest = numericValue(latestAtMs, NaN);
    if (isFinite(explicitLatest) && explicitLatest > 0)
      return explicitLatest;
    if (pointCount > 0)
      return latestPointMs();
    return Date.now();
  }

  function startTimestampMs() {
    if (pointCount === 0)
      return endTimestampMs();
    const windowSeconds = numericValue(graph && graph.window_seconds !== undefined ? graph.window_seconds : NaN, NaN);
    const latestMs = latestPointMs();
    if (isFinite(windowSeconds) && windowSeconds > 0)
      return Math.max(0, latestMs - (windowSeconds * 1000));
    return pointTimeMs(rawPoints[0]);
  }

  function latestPointMs() {
    if (pointCount === 0)
      return NaN;
    return pointTimeMs(rawPoints[pointCount - 1]);
  }

  function renderMinValue() {
    return 0;
  }

  function renderMaxValue() {
    return 100;
  }

  function resolvedEstimateWindowMs() {
    const seconds = numericValue(estimate && estimate.window_seconds !== undefined ? estimate.window_seconds : NaN, NaN);
    return isFinite(seconds) && seconds > 0 ? seconds * 1000 : NaN;
  }

  function projectionAvailable() {
    if (rawPoints.length < 1 || !estimate)
      return false;
    if (String(estimate.state || "") !== "available")
      return false;
    const minutes = numericValue(estimate.minutes_remaining, NaN);
    return isFinite(minutes) && minutes > 0 && isFinite(estimateWindowMs) && estimateWindowMs > 0;
  }

  function projectedEndTimestampMs() {
    if (!hasProjection || pointCount < 1)
      return NaN;
    const lastPointMs = latestPointMs();
    return lastPointMs + numericValue(estimate.minutes_remaining, 0) * 60 * 1000;
  }

  function projectedWindowStartTimestampMs() {
    if (!hasProjection || pointCount < 1)
      return NaN;
    return latestPointMs() - estimateWindowMs;
  }

  function formatEdgeLabel(timestampMs, spanMs) {
    const date = new Date(timestampMs);
    if (isNaN(date.getTime()))
      return "";

    let hours = date.getHours();
    const minutes = date.getMinutes();
    const suffix = hours >= 12 ? "pm" : "am";
    hours = hours % 12;
    if (hours === 0)
      hours = 12;

    if (spanMs <= 36 * 60 * 60 * 1000)
      return hours + ":" + (minutes < 10 ? "0" : "") + minutes + suffix;

    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return months[date.getMonth()] + " " + date.getDate();
  }

  onGraphChanged: graphCanvas.requestPaint()
  onAccentColorChanged: graphCanvas.requestPaint()
  onLatestAtMsChanged: graphCanvas.requestPaint()
  onResolvedStartMsChanged: graphCanvas.requestPaint()
  onResolvedEndMsChanged: graphCanvas.requestPaint()
  onResolvedMaxValueChanged: graphCanvas.requestPaint()
  onResolvedMinValueChanged: graphCanvas.requestPaint()
  onEstimateChanged: graphCanvas.requestPaint()
  onWidthChanged: graphCanvas.requestPaint()
  onHeightChanged: graphCanvas.requestPaint()

  Rectangle {
    id: graphSurface
    anchors.left: parent.left
    anchors.right: parent.right
    height: root.surfaceHeight
    radius: Style.radiusM
    color: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.05)
    border.width: Style.capsuleBorderWidth
    border.color: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.18)

    Canvas {
      id: graphCanvas
      anchors.fill: parent
      anchors.margins: Style.marginS
      visible: root.canRenderGraph

      onPaint: {
        const ctx = getContext("2d");
        ctx.clearRect(0, 0, width, height);
        if (!root.canRenderGraph)
          return;

        const padX = 4 * Style.uiScaleRatio;
        const padY = 4 * Style.uiScaleRatio;
        const plotWidth = width - (padX * 2);
        const plotHeight = height - (padY * 2);
        if (plotWidth <= 0 || plotHeight <= 0)
          return;

        const minTs = root.resolvedStartMs;
        const maxTs = root.resolvedEndMs;
        const span = Math.max(1, maxTs - minTs);
        const minValue = root.resolvedMinValue;
        const maxValue = root.resolvedMaxValue;
        const valueSpan = Math.max(1, maxValue - minValue);
        const segments = [];
        let lastCoord = null;

        for (let i = 0; i < 3; ++i) {
          const fraction = i / 2;
          const y = padY + (plotHeight * fraction);
          ctx.strokeStyle = Qt.rgba(Color.mOutline.r, Color.mOutline.g, Color.mOutline.b, 0.14);
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(padX, y);
          ctx.lineTo(padX + plotWidth, y);
          ctx.stroke();
        }

        if (root.hasProjection && root.projectionWindowStartMs > minTs && root.projectionWindowStartMs < maxTs) {
          const guideX = padX + Math.max(0, Math.min(1, (root.projectionWindowStartMs - minTs) / span)) * plotWidth;
          ctx.strokeStyle = Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.22);
          ctx.lineWidth = 1;
          ctx.setLineDash([3 * Style.uiScaleRatio, 4 * Style.uiScaleRatio]);
          ctx.beginPath();
          ctx.moveTo(guideX, padY);
          ctx.lineTo(guideX, padY + plotHeight);
          ctx.stroke();
          ctx.setLineDash([]);
        }

        for (let segmentIndex = 0; segmentIndex < root.graphSegments.length; ++segmentIndex) {
          const segment = root.graphSegments[segmentIndex];
          const coords = [];
          for (let i = 0; i < segment.length; ++i) {
            const point = segment[i];
            const frac = (root.pointTimeMs(point) - minTs) / span;
            const x = padX + Math.max(0, Math.min(1, frac)) * plotWidth;
            const clampedValue = Math.max(minValue, Math.min(maxValue, Number(point.value)));
            const y = padY + plotHeight * (1 - ((clampedValue - minValue) / valueSpan));
            coords.push({ x: x, y: y });
          }
          segments.push(coords);
        }

        const fill = ctx.createLinearGradient(0, padY, 0, padY + plotHeight);
        fill.addColorStop(0, Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.22));
        fill.addColorStop(1, Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.02));

        ctx.strokeStyle = root.accentColor;
        ctx.lineWidth = 2 * Style.uiScaleRatio;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";

        for (let segmentIndex = 0; segmentIndex < segments.length; ++segmentIndex) {
          const coords = segments[segmentIndex];
          if (coords.length === 0)
            continue;

          lastCoord = coords[coords.length - 1];
          if (coords.length >= 2) {
            ctx.beginPath();
            ctx.moveTo(coords[0].x, padY + plotHeight);
            for (let i = 0; i < coords.length; ++i)
              ctx.lineTo(coords[i].x, coords[i].y);
            ctx.lineTo(coords[coords.length - 1].x, padY + plotHeight);
            ctx.closePath();
            ctx.fillStyle = fill;
            ctx.fill();

            ctx.beginPath();
            ctx.moveTo(coords[0].x, coords[0].y);
            for (let i = 1; i < coords.length; ++i)
              ctx.lineTo(coords[i].x, coords[i].y);
            ctx.stroke();
          }
        }

        if (!lastCoord)
          return;

        if (root.hasProjection) {
          const projectedX = padX + Math.max(0, Math.min(1, (root.projectionEndMs - minTs) / span)) * plotWidth;
          const projectedY = padY + plotHeight;
          ctx.strokeStyle = Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.8);
          ctx.lineWidth = 2 * Style.uiScaleRatio;
          ctx.setLineDash([1 * Style.uiScaleRatio, 5 * Style.uiScaleRatio]);
          ctx.beginPath();
          ctx.moveTo(lastCoord.x, lastCoord.y);
          ctx.lineTo(projectedX, projectedY);
          ctx.stroke();
          ctx.setLineDash([]);
        }

        ctx.fillStyle = root.accentColor;
        ctx.beginPath();
        ctx.arc(lastCoord.x, lastCoord.y, 3 * Style.uiScaleRatio, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    NText {
      anchors.centerIn: parent
      visible: !root.canRenderGraph
      text: root.pointCount > 0 ? root.sparseLabel : root.emptyLabel
      pointSize: Style.fontSizeXS
      color: Color.mOnSurfaceVariant
    }
  }

  Item {
    id: labelRow
    visible: root.canRenderGraph
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.top: graphSurface.bottom
    anchors.topMargin: Style.marginXS
    height: Math.max(startLabel.implicitHeight, endLabel.implicitHeight)

    NText {
      id: startLabel
      anchors.left: parent.left
      text: root.formatEdgeLabel(root.resolvedStartMs, root.resolvedSpanMs)
      pointSize: Style.fontSizeXXS
      font.family: Settings.data.ui.fontFixed
      color: Color.mOnSurfaceVariant
    }

    NText {
      id: endLabel
      anchors.right: parent.right
      text: root.formatEdgeLabel(root.resolvedEndMs, root.resolvedSpanMs)
      pointSize: Style.fontSizeXXS
      font.family: Settings.data.ui.fontFixed
      color: Color.mOnSurfaceVariant
    }
  }
}
