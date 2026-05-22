import QtQuick
import QtQuick.Layouts
import "TxTheme.js" as TxTheme
import qs.Commons
import qs.Widgets

Item {
  id: root

  property var pluginApi: null
  readonly property var geometryPlaceholder: mainContainer
  property real contentPreferredWidth: Math.round(820 * Style.uiScaleRatio)
  property real contentPreferredHeight: mainColumn.implicitHeight + Style.marginL * 2
  readonly property bool allowAttach: true
  readonly property real batteryCardHeight: Math.round(214 * Style.uiScaleRatio)
  readonly property real binaryToggleWidth: Math.round(60 * Style.uiScaleRatio)

  readonly property var mainInstance: pluginApi?.mainInstance
  readonly property string pluginName: pluginApi?.manifest?.name || "Hollyland"
  readonly property string pluginDescription: pluginApi?.manifest?.description || ""
  readonly property var state: mainInstance ? (mainInstance.state || ({})) : ({})
  readonly property var rx: state.rx || ({})
  readonly property var audio: state.audio || ({})
  readonly property var transmitters: state.transmitters || []
  readonly property var onlineTransmitters: transmitters.filter(function(tx) { return tx && tx.online === true; })
  readonly property var powerTransmitters: transmitters.filter(function(tx) { return tx && tx.power && typeof tx.power === "object"; })
  readonly property var panelTransmitters: transmitters.slice ? transmitters.slice(0, 2) : transmitters
  readonly property var panelPowerTransmitters: powerTransmitters.slice ? powerTransmitters.slice(0, 2) : powerTransmitters
  readonly property bool canIdentify: onlineTransmitters.length > 0
  readonly property bool controlsEnabled: !!mainInstance && !mainInstance.actionBusy

  function updatedLabel() {
    if (!mainInstance || !mainInstance.updatedAt) return "Waiting for service";
    const d = new Date(mainInstance.updatedAt);
    if (isNaN(d.getTime())) return "Waiting for service";
    return "Updated " + d.toLocaleTimeString();
  }

  function shutdownModeValue() {
    if ((audio.shutdown_time_name || audio.shutdown_time) === "quarter-hour")
      return "quarter";
    return audio.shutdown_time_name || audio.shutdown_time;
  }

  function parseIsoMs(value) {
    if (!value) return NaN;
    const parsed = Date.parse(value);
    return isNaN(parsed) ? NaN : parsed;
  }

  function capitalizeLabel(value) {
    if (!value) return "";
    const text = String(value);
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  function formatClockTime(timestampMs) {
    const date = new Date(timestampMs);
    if (isNaN(date.getTime())) return "";
    let hours = date.getHours();
    const minutes = date.getMinutes();
    const suffix = hours >= 12 ? "pm" : "am";
    hours = hours % 12;
    if (hours === 0) hours = 12;
    return hours + ":" + (minutes < 10 ? "0" : "") + minutes + suffix;
  }

  function formatDurationMinutes(totalMinutes) {
    const numeric = Number(totalMinutes);
    if (!isFinite(numeric) || numeric < 0) return "";
    const rounded = Math.max(0, Math.round(numeric));
    const days = Math.floor(rounded / (24 * 60));
    const hours = Math.floor((rounded % (24 * 60)) / 60);
    const minutes = rounded % 60;
    if (days > 0) return days + "d" + (hours > 0 ? " " + hours + "h" : "");
    if (hours > 0 && minutes > 0) return hours + "h " + minutes + "m";
    if (hours > 0) return hours + "h";
    return minutes + "m";
  }

  function formatDurationSeconds(totalSeconds) {
    const numeric = Number(totalSeconds);
    if (!isFinite(numeric) || numeric <= 0) return "";
    return formatDurationMinutes(numeric / 60);
  }

  function formatRatePerHour(rateValue) {
    const numeric = Number(rateValue);
    if (!isFinite(numeric) || numeric <= 0) return "";
    const rounded = Math.abs(numeric - Math.round(numeric)) < 0.05
      ? String(Math.round(numeric))
      : numeric.toFixed(1);
    return rounded + "%/h";
  }

  function batteryPercentLabel(tx) {
    if (tx && tx.online === false)
      return "Off";
    if (!tx || tx.battery === undefined || tx.battery === null || tx.battery === "")
      return "-";
    const numeric = Number(tx.battery);
    return isFinite(numeric) ? (Math.round(numeric) + "%") : String(tx.battery);
  }

  function txAccentColor(tx) {
    return TxTheme.accentColorForTx(tx && tx.id ? String(tx.id) : "");
  }

  function txStateLabel(tx) {
    if (tx && tx.online === true) return "Online";
    if (tx && tx.online === false) return "Offline";
    return "Waiting";
  }

  function txCardDetail(tx) {
    if (!tx) return "Waiting for transmitter state";
    if (tx.online === true) return "Receiver link active";
    if (tx.online === false) return "Receiver link unavailable";
    return "Waiting for transmitter state";
  }

  function txAudioStatusLabel(tx) {
    if (!tx || tx.online !== true) return "Off";
    return tx.mute === true ? "Muted" : "Audio On";
  }

  function powerAccentColor(tx) {
    return txAccentColor(tx);
  }

  function powerGraphEmptyLabel(graph) {
    if (graph && graph.stale === true) return "No recent samples";
    const pointCount = graph && graph.points && graph.points.length ? graph.points.length : 0;
    return pointCount > 0 ? "Need more samples" : "No history yet";
  }

  function powerTrendLabel(tx) {
    const trend = tx && tx.power ? String(tx.power.trend || "") : "";
    if (trend === "discharging") return "Discharging";
    if (trend === "charging") return "Charging";
    if (trend === "steady") return "Stable";
    if (tx && tx.online === false) return "Offline";
    if (tx && tx.online === true) return "Online";
    return "";
  }

  function powerUpdatedLabel(tx) {
    const power = tx && tx.power ? tx.power : ({});
    const timestampMs = parseIsoMs(power.latest_at);
    if (!isFinite(timestampMs)) return "";
    return "Updated " + formatClockTime(timestampMs);
  }

  function powerCardSubtitle(tx) {
    const power = tx && tx.power ? tx.power : ({});
    const graph = power.graph || ({});
    const parts = [];
    parts.push(graph.label ? String(graph.label) : "Battery");
    const trend = powerTrendLabel(tx);
    if (trend !== "") parts.push(trend);
    const updated = powerUpdatedLabel(tx);
    if (updated !== "") parts.push(updated);
    return parts.join("  |  ");
  }

  function powerEstimateHeadline(tx) {
    const power = tx && tx.power ? tx.power : ({});
    const estimate = power.estimate || ({});
    const state = estimate.state ? String(estimate.state) : "";
    if (state === "available") {
      const etaLabel = formatDurationMinutes(estimate.minutes_remaining);
      return etaLabel !== "" ? ("ETA " + etaLabel) : "ETA";
    }
    if (state === "learning") return "Estimating";
    if (state === "charging") return "Charging";
    if (state === "steady") return "Stable";
    if (state === "unavailable") return "No estimate";
    return "No estimate";
  }

  function powerEstimateDetail(tx) {
    const power = tx && tx.power ? tx.power : ({});
    const estimate = power.estimate || ({});
    if (estimate.note) return String(estimate.note);

    const state = estimate.state ? String(estimate.state) : "";
    if (state === "available") {
      const rateLabel = formatRatePerHour(estimate.rate_percent_per_hour);
      const windowLabel = formatDurationSeconds(estimate.window_seconds);
      let text = "";
      if (rateLabel !== "" && windowLabel !== "")
        text = rateLabel + " over " + windowLabel;
      else
        text = rateLabel || windowLabel;

      if (estimate.confidence && String(estimate.confidence) !== "high") {
        const confidenceLabel = capitalizeLabel(estimate.confidence) + " confidence";
        text = text !== "" ? (text + "  |  " + confidenceLabel) : confidenceLabel;
      }
      if (text !== "") return text;
    }

    return powerUpdatedLabel(tx);
  }

  anchors.fill: parent

  Rectangle {
    id: mainContainer
    anchors.fill: parent
    color: "transparent"

    ColumnLayout {
      id: mainColumn
      anchors.fill: parent
      anchors.margins: Style.marginL
      spacing: Style.marginM

      NBox {
        id: headerBox
        Layout.fillWidth: true
        implicitHeight: headerRow.implicitHeight + Style.marginL

        RowLayout {
          id: headerRow
          anchors.fill: parent
          anchors.margins: Style.marginM
          spacing: Style.marginM

          Rectangle {
            width: Style.fontSizeXXL * 1.2
            height: width
            radius: Style.radiusL
            color: Qt.rgba(mainInstance ? mainInstance.statusColor().r : Color.mPrimary.r,
                           mainInstance ? mainInstance.statusColor().g : Color.mPrimary.g,
                           mainInstance ? mainInstance.statusColor().b : Color.mPrimary.b,
                           0.14)
            border.width: 1
            border.color: mainInstance ? mainInstance.statusColor() : Color.mPrimary

            Rectangle {
              width: Math.max(8, Style.toOdd(parent.width * 0.22))
              height: width
              radius: width / 2
              color: mainInstance ? mainInstance.statusColor() : Color.mPrimary
              anchors.centerIn: parent
            }
          }

          ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            NText {
              text: root.pluginName
              pointSize: Style.fontSizeL
              font.weight: Style.fontWeightBold
              color: Color.mOnSurface
            }

            NText {
              text: (mainInstance ? mainInstance.statusLabel() : "Waiting") + "  |  " + root.updatedLabel()
              pointSize: Style.fontSizeXS
              color: Color.mOnSurfaceVariant
            }
          }

          NIconButton {
            icon: "refresh"
            baseSize: Style.baseWidgetSize * 0.8
            onClicked: {
              if (root.mainInstance) root.mainInstance.refreshState();
            }
          }

          NIconButton {
            icon: "close"
            baseSize: Style.baseWidgetSize * 0.8
            onClicked: {
              if (pluginApi) pluginApi.withCurrentScreen(function(screen) {
                pluginApi.closePanel(screen);
              });
            }
          }
        }
      }

      NBox {
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignTop
        implicitHeight: controlsColumn.implicitHeight + Style.marginL

        ColumnLayout {
          id: controlsColumn
          anchors.fill: parent
          anchors.margins: Style.marginM
          spacing: Style.marginM

          NText {
            text: "Controls"
            pointSize: Style.fontSizeS
            font.weight: Style.fontWeightBold
            color: Color.mOnSurface
          }

          RowLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            spacing: Style.marginL

            ColumnLayout {
              Layout.fillWidth: true
              Layout.alignment: Qt.AlignTop
              spacing: Style.marginS

              RowLayout {
                Layout.fillWidth: true
                spacing: Style.marginS

                ColumnLayout {
                  Layout.fillWidth: true
                  spacing: 2

                  NText { text: "Noise Reduction"; pointSize: Style.fontSizeS; color: Color.mOnSurface }
                  NText { text: "Uses the current CLI level value"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
                }

                Rectangle {
                  implicitWidth: root.binaryToggleWidth
                  implicitHeight: Math.round(34 * Style.uiScaleRatio)
                  radius: Style.radiusM
                  color: audio.noise_enabled !== true ? Color.mPrimary : "transparent"
                  border.width: 1
                  border.color: Color.mPrimary
                  opacity: root.controlsEnabled ? 1.0 : 0.6

                  NText {
                    anchors.centerIn: parent
                    text: "Off"
                    pointSize: Style.fontSizeS
                    color: audio.noise_enabled !== true ? Color.mOnPrimary : Color.mPrimary
                  }

                  MouseArea {
                    anchors.fill: parent
                    enabled: root.controlsEnabled
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: if (mainInstance) mainInstance.setBooleanAction("set-noise", false, { level: audio.noise_level || 2 });
                  }
                }

                Rectangle {
                  implicitWidth: root.binaryToggleWidth
                  implicitHeight: Math.round(34 * Style.uiScaleRatio)
                  radius: Style.radiusM
                  color: audio.noise_enabled === true ? Color.mPrimary : "transparent"
                  border.width: 1
                  border.color: Color.mPrimary
                  opacity: root.controlsEnabled ? 1.0 : 0.6

                  NText {
                    anchors.centerIn: parent
                    text: "On"
                    pointSize: Style.fontSizeS
                    color: audio.noise_enabled === true ? Color.mOnPrimary : Color.mPrimary
                  }

                  MouseArea {
                    anchors.fill: parent
                    enabled: root.controlsEnabled
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: if (mainInstance) mainInstance.setBooleanAction("set-noise", true, { level: audio.noise_level || 2 });
                  }
                }
              }

              RowLayout {
                Layout.fillWidth: true
                spacing: Style.marginS

                ColumnLayout {
                  Layout.fillWidth: true
                  spacing: 2

                  NText { text: "Receiver Light"; pointSize: Style.fontSizeS; color: Color.mOnSurface }
                  NText { text: "Front light visibility"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
                }

                Rectangle {
                  implicitWidth: root.binaryToggleWidth
                  implicitHeight: Math.round(34 * Style.uiScaleRatio)
                  radius: Style.radiusM
                  color: audio.light_enabled !== true ? Color.mPrimary : "transparent"
                  border.width: 1
                  border.color: Color.mPrimary
                  opacity: root.controlsEnabled ? 1.0 : 0.6

                  NText {
                    anchors.centerIn: parent
                    text: "Off"
                    pointSize: Style.fontSizeS
                    color: audio.light_enabled !== true ? Color.mOnPrimary : Color.mPrimary
                  }

                  MouseArea {
                    anchors.fill: parent
                    enabled: root.controlsEnabled
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: if (mainInstance) mainInstance.setBooleanAction("set-light", false);
                  }
                }

                Rectangle {
                  implicitWidth: root.binaryToggleWidth
                  implicitHeight: Math.round(34 * Style.uiScaleRatio)
                  radius: Style.radiusM
                  color: audio.light_enabled === true ? Color.mPrimary : "transparent"
                  border.width: 1
                  border.color: Color.mPrimary
                  opacity: root.controlsEnabled ? 1.0 : 0.6

                  NText {
                    anchors.centerIn: parent
                    text: "On"
                    pointSize: Style.fontSizeS
                    color: audio.light_enabled === true ? Color.mOnPrimary : Color.mPrimary
                  }

                  MouseArea {
                    anchors.fill: parent
                    enabled: root.controlsEnabled
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: if (mainInstance) mainInstance.setBooleanAction("set-light", true);
                  }
                }
              }

              NText { text: "Voice mode"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
              RowLayout {
                Layout.fillWidth: true
                spacing: Style.marginS

                Repeater {
                  model: [
                    { label: "Mono", value: "mono" },
                    { label: "Stereo", value: "stereo" }
                  ]

                  delegate: Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    implicitHeight: Math.round(34 * Style.uiScaleRatio)
                    radius: Style.radiusM
                    color: (audio.voice_mode_name || audio.voice_mode) === modelData.value ? Color.mPrimary : "transparent"
                    border.width: 1
                    border.color: Color.mPrimary
                    opacity: root.controlsEnabled ? 1.0 : 0.6

                    NText {
                      anchors.centerIn: parent
                      text: modelData.label
                      pointSize: Style.fontSizeS
                      color: ((audio.voice_mode_name || audio.voice_mode) === modelData.value) ? Color.mOnPrimary : Color.mPrimary
                    }

                    MouseArea {
                      anchors.fill: parent
                      enabled: root.controlsEnabled
                      cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                      onClicked: if (mainInstance) mainInstance.runAction({ action: "set-voice-mode", mode: modelData.value });
                    }
                  }
                }
              }

              NText { text: "EQ"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
              RowLayout {
                Layout.fillWidth: true
                spacing: Style.marginS

                Repeater {
                  model: [
                    { label: "Overcast", value: "overcast" },
                    { label: "Bright", value: "bright" },
                    { label: "Balance", value: "balance" }
                  ]

                  delegate: Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    implicitHeight: Math.round(34 * Style.uiScaleRatio)
                    radius: Style.radiusM
                    color: (audio.eq_level_name || audio.eq_level) === modelData.value ? Color.mPrimary : "transparent"
                    border.width: 1
                    border.color: Color.mPrimary
                    opacity: root.controlsEnabled ? 1.0 : 0.6

                    NText {
                      anchors.centerIn: parent
                      text: modelData.label
                      pointSize: Style.fontSizeS
                      color: ((audio.eq_level_name || audio.eq_level) === modelData.value) ? Color.mOnPrimary : Color.mPrimary
                    }

                    MouseArea {
                      anchors.fill: parent
                      enabled: root.controlsEnabled
                      cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                      onClicked: if (mainInstance) mainInstance.runAction({ action: "set-eq", preset: modelData.value });
                    }
                  }
                }
              }

              NText { text: "Voice level"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
              RowLayout {
                Layout.fillWidth: true
                spacing: Style.marginS

                Rectangle {
                  implicitWidth: Math.round(40 * Style.uiScaleRatio)
                  implicitHeight: Math.round(34 * Style.uiScaleRatio)
                  radius: Style.radiusM
                  color: "transparent"
                  border.width: 1
                  border.color: Color.mPrimary
                  opacity: root.controlsEnabled ? 1.0 : 0.6

                  NText {
                    anchors.centerIn: parent
                    text: "-"
                    pointSize: Style.fontSizeS
                    color: Color.mPrimary
                  }

                  MouseArea {
                    anchors.fill: parent
                    enabled: root.controlsEnabled
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: if (mainInstance) mainInstance.setVoiceLevel(Math.max(mainInstance.voiceLevelMin, (audio.voice_level || 0) - 1));
                  }
                }

                Rectangle {
                  Layout.fillWidth: true
                  implicitHeight: valueText.implicitHeight + Style.marginS * 2
                  radius: Style.radiusM
                  color: Style.capsuleColor
                  border.color: Style.capsuleBorderColor
                  border.width: Style.capsuleBorderWidth

                  NText {
                    id: valueText
                    anchors.centerIn: parent
                    text: mainInstance ? mainInstance.displayValue(audio.voice_level, "-") : "-"
                    font.family: Settings.data.ui.fontFixed
                    pointSize: Style.fontSizeS
                    color: Color.mOnSurface
                  }
                }

                Rectangle {
                  implicitWidth: Math.round(40 * Style.uiScaleRatio)
                  implicitHeight: Math.round(34 * Style.uiScaleRatio)
                  radius: Style.radiusM
                  color: "transparent"
                  border.width: 1
                  border.color: Color.mPrimary
                  opacity: root.controlsEnabled ? 1.0 : 0.6

                  NText {
                    anchors.centerIn: parent
                    text: "+"
                    pointSize: Style.fontSizeS
                    color: Color.mPrimary
                  }

                  MouseArea {
                    anchors.fill: parent
                    enabled: root.controlsEnabled
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: if (mainInstance) mainInstance.setVoiceLevel(Math.min(mainInstance.voiceLevelMax, (audio.voice_level || 0) + 1));
                  }
                }
              }
            }

            ColumnLayout {
              Layout.fillWidth: true
              Layout.alignment: Qt.AlignTop
              spacing: Style.marginS

              RowLayout {
                Layout.fillWidth: true
                spacing: Style.marginS

                ColumnLayout {
                  Layout.fillWidth: true
                  spacing: 2

                  NText { text: "Performance Mode"; pointSize: Style.fontSizeS; color: Color.mOnSurface }
                  NText { text: "Receiver performance toggle"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
                }

                Rectangle {
                  implicitWidth: root.binaryToggleWidth
                  implicitHeight: Math.round(34 * Style.uiScaleRatio)
                  radius: Style.radiusM
                  color: rx.performance_enabled !== true ? Color.mPrimary : "transparent"
                  border.width: 1
                  border.color: Color.mPrimary
                  opacity: root.controlsEnabled ? 1.0 : 0.6

                  NText {
                    anchors.centerIn: parent
                    text: "Off"
                    pointSize: Style.fontSizeS
                    color: rx.performance_enabled !== true ? Color.mOnPrimary : Color.mPrimary
                  }

                  MouseArea {
                    anchors.fill: parent
                    enabled: root.controlsEnabled
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: if (mainInstance) mainInstance.setBooleanAction("set-performance", false);
                  }
                }

                Rectangle {
                  implicitWidth: root.binaryToggleWidth
                  implicitHeight: Math.round(34 * Style.uiScaleRatio)
                  radius: Style.radiusM
                  color: rx.performance_enabled === true ? Color.mPrimary : "transparent"
                  border.width: 1
                  border.color: Color.mPrimary
                  opacity: root.controlsEnabled ? 1.0 : 0.6

                  NText {
                    anchors.centerIn: parent
                    text: "On"
                    pointSize: Style.fontSizeS
                    color: rx.performance_enabled === true ? Color.mOnPrimary : Color.mPrimary
                  }

                  MouseArea {
                    anchors.fill: parent
                    enabled: root.controlsEnabled
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: if (mainInstance) mainInstance.setBooleanAction("set-performance", true);
                  }
                }
              }

              RowLayout {
                Layout.fillWidth: true
                spacing: Style.marginS

                ColumnLayout {
                  Layout.fillWidth: true
                  spacing: 2

                  NText { text: "TX Identify"; pointSize: Style.fontSizeS; color: Color.mOnSurface }
                  NText { text: "Locate paired transmitter"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
                }

                Rectangle {
                  implicitWidth: root.binaryToggleWidth
                  implicitHeight: Math.round(34 * Style.uiScaleRatio)
                  radius: Style.radiusM
                  color: !((mainInstance && mainInstance.actionBusy && mainInstance.pendingAction === "set-tx-identify")
                       || audio.tx_identify_enabled === true) ? Color.mPrimary : "transparent"
                  border.width: 1
                  border.color: Color.mPrimary
                  opacity: (root.controlsEnabled && root.canIdentify) ? 1.0 : 0.6

                  NText {
                    anchors.centerIn: parent
                    text: "Off"
                    pointSize: Style.fontSizeS
                    color: !((mainInstance && mainInstance.actionBusy && mainInstance.pendingAction === "set-tx-identify")
                         || audio.tx_identify_enabled === true) ? Color.mOnPrimary : Color.mPrimary
                  }

                  MouseArea {
                    anchors.fill: parent
                    enabled: root.controlsEnabled && root.canIdentify
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: if (mainInstance) mainInstance.setBooleanAction("set-tx-identify", false);
                  }
                }

                Rectangle {
                  implicitWidth: root.binaryToggleWidth
                  implicitHeight: Math.round(34 * Style.uiScaleRatio)
                  radius: Style.radiusM
                  color: (mainInstance && mainInstance.actionBusy && mainInstance.pendingAction === "set-tx-identify")
                       || audio.tx_identify_enabled === true ? Color.mPrimary : "transparent"
                  border.width: 1
                  border.color: Color.mPrimary
                  opacity: (root.controlsEnabled && root.canIdentify) ? 1.0 : 0.6

                  NText {
                    anchors.centerIn: parent
                    text: "On"
                    pointSize: Style.fontSizeS
                    color: ((mainInstance && mainInstance.actionBusy && mainInstance.pendingAction === "set-tx-identify")
                         || audio.tx_identify_enabled === true) ? Color.mOnPrimary : Color.mPrimary
                  }

                  MouseArea {
                    anchors.fill: parent
                    enabled: root.controlsEnabled && root.canIdentify
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: if (mainInstance) mainInstance.setBooleanAction("set-tx-identify", true);
                  }
                }
              }

              NText { text: "Signal mode"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
              RowLayout {
                Layout.fillWidth: true
                spacing: Style.marginS

                Repeater {
                  model: [
                    { label: "Normal", value: "normal" },
                    { label: "Enhance", value: "enhance" }
                  ]

                  delegate: Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    implicitHeight: Math.round(34 * Style.uiScaleRatio)
                    radius: Style.radiusM
                    color: (audio.signal_mode_name || audio.signal_mode) === modelData.value ? Color.mPrimary : "transparent"
                    border.width: 1
                    border.color: Color.mPrimary
                    opacity: root.controlsEnabled ? 1.0 : 0.6

                    NText {
                      anchors.centerIn: parent
                      text: modelData.label
                      pointSize: Style.fontSizeS
                      color: ((audio.signal_mode_name || audio.signal_mode) === modelData.value) ? Color.mOnPrimary : Color.mPrimary
                    }

                    MouseArea {
                      anchors.fill: parent
                      enabled: root.controlsEnabled
                      cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                      onClicked: if (mainInstance) mainInstance.runAction({ action: "set-signal-mode", mode: modelData.value });
                    }
                  }
                }
              }

              NText { text: "Shutdown"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
              RowLayout {
                Layout.fillWidth: true
                spacing: Style.marginS

                Repeater {
                  model: [
                    { label: "15 min", value: "quarter" },
                    { label: "Never", value: "never" }
                  ]

                  delegate: Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    implicitHeight: Math.round(34 * Style.uiScaleRatio)
                    radius: Style.radiusM
                    color: root.shutdownModeValue() === modelData.value ? Color.mPrimary : "transparent"
                    border.width: 1
                    border.color: Color.mPrimary
                    opacity: root.controlsEnabled ? 1.0 : 0.6

                    NText {
                      anchors.centerIn: parent
                      text: modelData.label
                      pointSize: Style.fontSizeS
                      color: (root.shutdownModeValue() === modelData.value) ? Color.mOnPrimary : Color.mPrimary
                    }

                    MouseArea {
                      anchors.fill: parent
                      enabled: root.controlsEnabled
                      cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                      onClicked: if (mainInstance) mainInstance.runAction({ action: "set-shutdown-time", mode: modelData.value });
                    }
                  }
                }
              }
            }
          }
        }
      }

      RowLayout {
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignTop
        spacing: Style.marginM

        Repeater {
          model: panelTransmitters

          delegate: NBox {
            required property var modelData
            readonly property color accentColor: root.txAccentColor(modelData)
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            implicitHeight: txCardColumn.implicitHeight + Style.marginL

            ColumnLayout {
              id: txCardColumn
              anchors.fill: parent
              anchors.margins: Style.marginM
              spacing: Style.marginXS

              RowLayout {
                Layout.fillWidth: true
                spacing: Style.marginM

                Rectangle {
                  width: 10
                  height: 10
                  radius: 5
                  color: accentColor
                  opacity: modelData.online === false ? 0.55 : 1.0
                }

                ColumnLayout {
                  Layout.fillWidth: true
                  spacing: 2

                  NText {
                    text: modelData.label || "TX"
                    pointSize: Style.fontSizeS
                    font.weight: Style.fontWeightBold
                    color: Color.mOnSurface
                  }

                  NText {
                    text: root.txStateLabel(modelData)
                    pointSize: Style.fontSizeXS
                    font.weight: Style.fontWeightBold
                    color: accentColor
                  }
                }

                Rectangle {
                  implicitWidth: Math.round(92 * Style.uiScaleRatio)
                  implicitHeight: Math.round(32 * Style.uiScaleRatio)
                  radius: Style.radiusM
                  color: modelData.mute === true ? accentColor : "transparent"
                  border.width: 1
                  border.color: accentColor
                  opacity: (root.controlsEnabled && modelData.online === true) ? 1.0 : 0.5

                  NText {
                    anchors.centerIn: parent
                    text: root.txAudioStatusLabel(modelData)
                    pointSize: Style.fontSizeXS
                    font.weight: Style.fontWeightBold
                    color: modelData.mute === true ? Color.mOnPrimary : accentColor
                  }

                  MouseArea {
                    anchors.fill: parent
                    enabled: root.controlsEnabled && modelData.online === true
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: if (mainInstance) mainInstance.runAction({ action: "set-tx-mute", tx: modelData.id, on: modelData.mute !== true });
                  }
                }
              }

              NText {
                text: root.txCardDetail(modelData)
                pointSize: Style.fontSizeXS
                color: Color.mOnSurfaceVariant
              }
            }
          }
        }

        NBox {
          visible: panelTransmitters.length === 0
          Layout.fillWidth: true
          Layout.alignment: Qt.AlignTop
          implicitHeight: txEmptyText.implicitHeight + Style.marginL

          NText {
            id: txEmptyText
            anchors.fill: parent
            anchors.margins: Style.marginM
            text: "No transmitter state reported yet."
            pointSize: Style.fontSizeXS
            color: Color.mOnSurfaceVariant
          }
        }
      }

      RowLayout {
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignTop
        spacing: Style.marginM

        Repeater {
          model: panelPowerTransmitters

          delegate: Rectangle {
            id: batteryCard
            required property var modelData
            readonly property var power: modelData && modelData.power ? modelData.power : ({})
            readonly property var graph: power.graph || ({})
            readonly property color accentColor: root.powerAccentColor(modelData)
            readonly property string secondaryText: root.powerEstimateDetail(modelData)
            readonly property string subtitleText: root.powerCardSubtitle(modelData)
            readonly property string graphEmptyLabel: root.powerGraphEmptyLabel(graph)

            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            implicitHeight: Math.max(batteryCardColumn.implicitHeight + Style.marginM, root.batteryCardHeight)
            radius: Style.radiusM
            color: Qt.rgba(accentColor.r, accentColor.g, accentColor.b, 0.05)
            border.width: 1
            border.color: Qt.rgba(accentColor.r, accentColor.g, accentColor.b, 0.24)

            ColumnLayout {
              id: batteryCardColumn
              anchors.fill: parent
              anchors.margins: Style.marginM
              spacing: Style.marginS

              RowLayout {
                Layout.fillWidth: true
                spacing: Style.marginS

                NText {
                  text: modelData.label || "TX"
                  pointSize: Style.fontSizeS
                  font.weight: Style.fontWeightBold
                  color: Color.mOnSurface
                  Layout.fillWidth: true
                }

                Rectangle {
                  Layout.alignment: Qt.AlignTop
                  radius: (batteryBadgeText.implicitHeight + Style.marginXS * 2) / 2
                  color: Qt.rgba(accentColor.r, accentColor.g, accentColor.b, 0.14)
                  border.width: 1
                  border.color: Qt.rgba(accentColor.r, accentColor.g, accentColor.b, 0.34)
                  implicitWidth: batteryBadgeText.implicitWidth + Style.marginM * 1.4
                  implicitHeight: batteryBadgeText.implicitHeight + Style.marginXS * 2

                  NText {
                    id: batteryBadgeText
                    anchors.centerIn: parent
                    text: root.batteryPercentLabel(modelData)
                    font.family: Settings.data.ui.fontFixed
                    pointSize: Style.fontSizeS
                    font.weight: Style.fontWeightBold
                    color: accentColor
                  }
                }
              }

              NText {
                visible: subtitleText !== ""
                text: subtitleText
                pointSize: Style.fontSizeXS
                color: Color.mOnSurfaceVariant
              }

              ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                NText {
                  text: root.powerEstimateHeadline(modelData)
                  pointSize: Style.fontSizeL
                  font.weight: Style.fontWeightBold
                  color: accentColor
                }

                NText {
                  visible: secondaryText !== ""
                  text: secondaryText
                  pointSize: Style.fontSizeXS
                  color: Color.mOnSurfaceVariant
                  wrapMode: Text.Wrap
                }
              }

              BatteryGraph {
                Layout.fillWidth: true
                graph: batteryCard.graph
                estimate: power.estimate
                latestAtMs: root.parseIsoMs(power.latest_at)
                accentColor: batteryCard.accentColor
                emptyLabel: batteryCard.graphEmptyLabel
                sparseLabel: batteryCard.graphEmptyLabel
              }
            }
          }
        }

        NBox {
          visible: panelPowerTransmitters.length === 0
          Layout.fillWidth: true
          Layout.alignment: Qt.AlignTop
          implicitHeight: batteryEmptyText.implicitHeight + Style.marginL

          NText {
            id: batteryEmptyText
            anchors.fill: parent
            anchors.margins: Style.marginM
            text: "No battery history reported yet."
            pointSize: Style.fontSizeXS
            color: Color.mOnSurfaceVariant
          }
        }
      }

      RowLayout {
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignTop
        spacing: Style.marginM

        NBox {
          Layout.fillWidth: true
          Layout.alignment: Qt.AlignTop
          implicitHeight: receiverDetailsColumn.implicitHeight + Style.marginL

          ColumnLayout {
            id: receiverDetailsColumn
            anchors.fill: parent
            anchors.margins: Style.marginM
            spacing: Style.marginS

            NText {
              text: "Receiver"
              pointSize: Style.fontSizeS
              font.weight: Style.fontWeightBold
              color: Color.mOnSurface
            }

            GridLayout {
              Layout.fillWidth: true
              columns: 2
              columnSpacing: Style.marginL
              rowSpacing: Style.marginS

              NText { text: "Version"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
              NText { text: mainInstance ? mainInstance.displayValue(rx.version) : "unknown"; pointSize: Style.fontSizeS; color: Color.mOnSurface }

              NText { text: "Serial"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
              NText { text: mainInstance ? mainInstance.displayValue(rx.sn) : "unknown"; pointSize: Style.fontSizeS; color: Color.mOnSurface }

              NText { text: "MAC"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
              NText { text: mainInstance ? mainInstance.displayValue(rx.mac) : "unknown"; pointSize: Style.fontSizeS; color: Color.mOnSurface }

              NText { text: "USB"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
              NText { text: mainInstance ? mainInstance.displayValue(rx.usb_dev) : "unknown"; pointSize: Style.fontSizeS; color: Color.mOnSurface }

              NText { text: "TX"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
              NText {
                text: onlineTransmitters.length > 0
                  ? onlineTransmitters.map(function(tx) {
                      const battery = (tx.battery === undefined || tx.battery === null) ? "-" : tx.battery;
                      return tx.label + " " + battery;
                    }).join("  |  ")
                  : "none online"
                pointSize: Style.fontSizeS
                color: Color.mOnSurface
                wrapMode: Text.Wrap
              }
            }
          }
        }

        NBox {
          Layout.fillWidth: true
          Layout.alignment: Qt.AlignTop
          implicitHeight: audioDetailsColumn.implicitHeight + Style.marginL

          ColumnLayout {
            id: audioDetailsColumn
            anchors.fill: parent
            anchors.margins: Style.marginM
            spacing: Style.marginS

            NText {
              text: "Audio"
              pointSize: Style.fontSizeS
              font.weight: Style.fontWeightBold
              color: Color.mOnSurface
            }

            GridLayout {
              Layout.fillWidth: true
              columns: 2
              columnSpacing: Style.marginL
              rowSpacing: Style.marginS

              NText { text: "Noise"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
              NText { text: mainInstance ? (mainInstance.boolText(audio.noise_enabled) + "  level " + mainInstance.displayValue(audio.noise_level, "-")) : "unknown"; pointSize: Style.fontSizeS; color: Color.mOnSurface }

              NText { text: "Voice"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
              NText { text: mainInstance ? (mainInstance.displayValue(audio.voice_mode_name || audio.voice_mode) + "  level " + mainInstance.displayValue(audio.voice_level, "-")) : "unknown"; pointSize: Style.fontSizeS; color: Color.mOnSurface }

              NText { text: "Signal"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
              NText { text: mainInstance ? mainInstance.displayValue(audio.signal_mode_name || audio.signal_mode) : "unknown"; pointSize: Style.fontSizeS; color: Color.mOnSurface }

              NText { text: "EQ"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
              NText { text: mainInstance ? mainInstance.displayValue(audio.eq_level_name || audio.eq_level) : "unknown"; pointSize: Style.fontSizeS; color: Color.mOnSurface }

              NText { text: "Shutdown"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
              NText { text: mainInstance ? mainInstance.displayValue(audio.shutdown_time_name || audio.shutdown_time) : "unknown"; pointSize: Style.fontSizeS; color: Color.mOnSurface }
            }
          }
        }
      }
    }

    Rectangle {
      id: feedbackToast
      visible: !!(mainInstance && mainInstance.bannerText)
      z: 2
      anchors.top: headerBox.bottom
      anchors.topMargin: Style.marginS
      anchors.right: mainColumn.right
      width: Math.min(mainColumn.width, Math.round(320 * Style.uiScaleRatio))
      implicitHeight: feedbackText.implicitHeight + Style.marginL
      radius: Style.radiusM
      color: Qt.rgba(mainInstance && mainInstance.bannerIsError ? Color.mError.r : Color.mPrimary.r,
                     mainInstance && mainInstance.bannerIsError ? Color.mError.g : Color.mPrimary.g,
                     mainInstance && mainInstance.bannerIsError ? Color.mError.b : Color.mPrimary.b,
                     0.12)
      border.width: 1
      border.color: mainInstance && mainInstance.bannerIsError ? Color.mError : Color.mPrimary

      NText {
        id: feedbackText
        anchors.fill: parent
        anchors.margins: Style.marginM
        wrapMode: Text.Wrap
        text: mainInstance ? mainInstance.bannerText : ""
        pointSize: Style.fontSizeXS
        color: mainInstance && mainInstance.bannerIsError ? Color.mError : Color.mPrimary
      }
    }
  }
}
