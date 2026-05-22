import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons

Item {
  id: root

  property var pluginApi: null

  property var current: ({})
  property var backend: ({})
  property var summary: ({})
  property var state: ({})
  property string updatedAt: ""
  property real currentTime: Date.now()
  property bool serviceAvailable: false
  property bool actionBusy: false
  property string pendingAction: ""
  property string transientErrorText: ""
  property string transientInfoText: ""
  property var _serviceRequest: null
  property var _actionRequest: null

  readonly property var manifest: pluginApi?.manifest || ({})
  readonly property string pluginId: manifest.id || "hollyland"
  readonly property string pluginName: manifest.name || "Hollyland"
  readonly property string pluginDescription: manifest.description || ""
  readonly property string cacheDir: Quickshell.env("HOME") + "/.cache/hollyland-widget"
  readonly property string stateFilePath: cacheDir + "/state.json"
  readonly property string serviceHost: (Quickshell.env("HOLLYLAND_WIDGET_HOST") || "127.0.0.1")
  readonly property string servicePort: (Quickshell.env("HOLLYLAND_WIDGET_PORT") || "8791")
  readonly property string currentUrl: "http://" + serviceHost + ":" + servicePort + "/api/current"
  readonly property string actionUrl: "http://" + serviceHost + ":" + servicePort + "/api/action"
  readonly property string bannerText: transientErrorText || transientInfoText || ((state && state.service_error) ? state.service_error : "")
  readonly property bool bannerIsError: !!(transientErrorText || (state && state.service_error))
  readonly property int voiceLevelMin: 0
  readonly property int voiceLevelMax: 5

  function displayValue(value, fallback) {
    return (value === undefined || value === null || value === "") ? (fallback || "unknown") : value;
  }

  function boolText(value) {
    if (value === true) return "on";
    if (value === false) return "off";
    return "unknown";
  }

  function statusColor() {
    if (bannerIsError) return Color.mError;
    if (bannerText) return Color.mPrimary;
    if (state && state.connected) return Color.mPrimary;
    if (state && state.device_present) return Color.mTertiary;
    return Color.mOnSurfaceVariant;
  }

  function statusLabel() {
    if (bannerIsError) return "Error";
    if (bannerText) return "Updated";
    if (state && state.connected) return "Live";
    if (state && state.device_present) return "Receiver found";
    return "Waiting";
  }

  function actionLabel(action) {
    if (!action) return "Action";
    return String(action).replace(/-/g, " ");
  }

  function extractErrorText(rawText, fallback) {
    if (!rawText || rawText.length === 0) return fallback;
    try {
      const parsed = JSON.parse(rawText);
      if (parsed && parsed.error) return String(parsed.error);
    } catch (_ignore) {}
    return rawText;
  }

  function actionSuccessText(action, parsed) {
    const currentState = parsed && parsed.current && parsed.current.state ? parsed.current.state : ({});
    const audioState = currentState.audio || ({});
    if (action === "set-tx-identify")
      return "TX identify sent" + (audioState.tx_identify_enabled === true ? " and device reports on" : "");
    if (action === "set-voice-level")
      return "Voice level set to " + displayValue(audioState.voice_level, "-");
    return "Applied " + actionLabel(action);
  }

  function primaryTx() {
    return (state && state.primary_tx) ? state.primary_tx : null;
  }

  function onlineTransmitters() {
    const items = (state && state.transmitters) ? state.transmitters : [];
    return items.filter(function(tx) { return tx && tx.online === true; });
  }

  function barAlertLevel() {
    const online = onlineTransmitters();
    let sawWarning = false;
    for (let i = 0; i < online.length; ++i) {
      if (online[i].alert_level === "critical")
        return "critical";
      if (online[i].alert_level === "warning")
        sawWarning = true;
    }
    return sawWarning ? "warning" : "none";
  }

  function shortTxLabel(tx) {
    if (!tx || !tx.id) return "TX";
    return String(tx.id).toUpperCase();
  }

  function transmitterBatteryCompactText(tx) {
    if (!tx)
      return "-";
    if (tx.online === false)
      return "Off";
    if (tx.battery === undefined || tx.battery === null || tx.battery === "")
      return "-";
    const numeric = Number(tx.battery);
    return isFinite(numeric) ? String(Math.round(numeric)) : String(tx.battery);
  }

  function transmitterBatteryText(tx) {
    const compact = transmitterBatteryCompactText(tx);
    if (compact === "Off" || compact === "-")
      return compact;
    return compact + "%";
  }

  function barTransmitterItems() {
    const items = (state && state.transmitters) ? state.transmitters : [];
    const clipped = items.slice ? items.slice(0, 2) : items;
    return clipped.map(function(tx) {
      return {
        id: tx && tx.id ? String(tx.id) : "",
        label: shortTxLabel(tx),
        valueText: transmitterBatteryCompactText(tx),
      };
    });
  }

  function barPrimaryText() {
    const online = onlineTransmitters();
    if (online.length === 2)
      return online.map(function(tx) { return shortTxLabel(tx); }).join("+");
    if (online.length > 2)
      return String(online.length) + "TX";
    const tx = primaryTx();
    if (tx && tx.label) return tx.label;
    if (state && state.connected) return "RX";
    return "HL";
  }

  function barSecondaryText() {
    const online = onlineTransmitters();
    if (online.length === 2) {
      return online.map(function(tx) {
        return transmitterBatteryCompactText(tx);
      }).join("/");
    }
    if (online.length > 2)
      return String(online.length) + " on";
    const tx = primaryTx();
    if (tx) return transmitterBatteryCompactText(tx);
    if (state && state.connected) return "LIVE";
    if (state && state.device_present) return "USB";
    return "";
  }

  function transmitterSummary(tx) {
    if (!tx) return "No transmitter detected";
    let text = tx.label + ": ";
    if (tx.online === true) text += "online";
    else if (tx.online === false) text += "offline";
    else text += "unknown";
    const batteryText = transmitterBatteryText(tx);
    if (batteryText !== "-") text += ", battery " + batteryText;
    if (tx.mute !== undefined && tx.mute !== null) text += ", mute " + boolText(tx.mute);
    return text;
  }

  function tooltipText() {
    let text = pluginName + " - " + statusLabel();
    const rx = (state && state.rx) ? state.rx : ({});
    const audio = (state && state.audio) ? state.audio : ({});
    const items = (state && state.transmitters) ? state.transmitters : [];
    text += "\nVersion: " + displayValue(rx.version);
    text += "\nNoise: " + boolText(audio.noise_enabled) + " (" + displayValue(audio.noise_level, "-") + ")";
    text += "\nVoice: " + displayValue(audio.voice_mode_name || audio.voice_mode);
    text += "\nSignal: " + displayValue(audio.signal_mode_name || audio.signal_mode);
    if (items.length > 0) {
      for (let i = 0; i < items.length; ++i)
        text += "\n" + transmitterSummary(items[i]);
    } else {
      text += "\n" + transmitterSummary(primaryTx());
    }
    if (bannerText) text += "\n" + bannerText;
    return text;
  }

  function applyCurrentPayload(payload, sourceLabel) {
    if (!payload || typeof payload !== "object") {
      transientErrorText = sourceLabel + " payload was not an object";
      return;
    }

    current = payload;
    backend = payload.backend || ({});
    summary = payload.summary || ({});
    state = payload.state || ({});
    updatedAt = payload.updated_at || "";
    serviceAvailable = sourceLabel === "Service";
    if (sourceLabel === "Service") {
      transientErrorText = "";
      if (!actionBusy)
        transientInfoText = "";
    }
    currentTime = Date.now();
  }

  function applyStatePayload(rawText, sourceLabel) {
    if (!rawText) {
      transientErrorText = sourceLabel + " returned an empty payload";
      return;
    }

    try {
      const parsed = JSON.parse(rawText);
      applyCurrentPayload(parsed, sourceLabel);
    } catch (e) {
      transientErrorText = sourceLabel + " failed to parse payload: " + e;
      Logger.e(pluginId, transientErrorText);
    }
  }

  function refreshState() {
    if (_serviceRequest) {
      try {
        _serviceRequest.abort();
      } catch (_ignore) {}
    }

    const xhr = new XMLHttpRequest();
    _serviceRequest = xhr;
    xhr.onreadystatechange = function() {
      if (xhr.readyState !== XMLHttpRequest.DONE) return;

      if (xhr.status >= 200 && xhr.status < 300) {
        applyStatePayload(xhr.responseText, "Service");
      } else {
        serviceAvailable = false;
        transientErrorText = xhr.responseText && xhr.responseText.length > 0 ? xhr.responseText : "Service unavailable";
        stateFile.reload();
      }
    };
    xhr.open("GET", currentUrl, true);
    xhr.send();
  }

  function runAction(payload) {
    if (actionBusy) return;

    const xhr = new XMLHttpRequest();
    _actionRequest = xhr;
    const actionName = payload && payload.action ? payload.action : "action";
    actionBusy = true;
    pendingAction = actionName;
    transientErrorText = "";
    transientInfoText = "";

    xhr.onreadystatechange = function() {
      if (xhr.readyState !== XMLHttpRequest.DONE) return;

      actionBusy = false;
      pendingAction = "";

      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const parsed = JSON.parse(xhr.responseText);
          if (parsed.current) {
            applyCurrentPayload(parsed.current, "Service");
            transientInfoText = actionSuccessText(actionName, parsed);
            feedbackClearTimer.restart();
          } else if (parsed.ok === false && parsed.error) {
            transientErrorText = parsed.error;
          } else {
            transientInfoText = "Applied " + actionLabel(actionName);
            feedbackClearTimer.restart();
          }
        } catch (e) {
          transientErrorText = "Failed to parse action response: " + e;
        }
      } else {
        transientErrorText = extractErrorText(xhr.responseText, "Action failed");
        refreshState();
      }
    };

    xhr.open("POST", actionUrl, true);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.send(JSON.stringify(payload || ({ action: "refresh" })));
  }

  function setBooleanAction(action, checked, extras) {
    const payload = { action: action, on: checked };
    if (extras) {
      for (const key in extras)
        payload[key] = extras[key];
    }
    runAction(payload);
  }

  function setVoiceLevel(value) {
    const clamped = Math.max(voiceLevelMin, Math.min(voiceLevelMax, value));
    runAction({ action: "set-voice-level", value: clamped });
  }

  Timer {
    interval: 5000
    running: true
    repeat: true
    onTriggered: {
      currentTime = Date.now();
      refreshState();
    }
  }

  Timer {
    id: feedbackClearTimer
    interval: 5000
    repeat: false
    onTriggered: {
      transientInfoText = "";
    }
  }

  FileView {
    id: stateFile
    path: root.stateFilePath

    onLoaded: {
      applyStatePayload(text(), "Fallback state file");
    }

    onLoadFailed: function(error) {
      Logger.w(pluginId, "state.json not found: " + error);
    }
  }

  IpcHandler {
    target: "plugin:hollyland"

    function toggle() {
      if (pluginApi) {
        pluginApi.withCurrentScreen(function(screen) {
          pluginApi.togglePanel(screen);
        });
      }
    }

    function refresh() {
      refreshState();
    }
  }

  Component.onCompleted: {
    Logger.i(pluginId, "Plugin initialized");
    refreshState();
  }
}
