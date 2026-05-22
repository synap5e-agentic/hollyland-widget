import QtQuick
import "qml" as HollylandUi

Item {
  id: root

  property var pluginApi: null

  readonly property var mainInstance: pluginApi?.mainInstance
  readonly property var geometryPlaceholder: panel.geometryPlaceholder
  property real contentPreferredWidth: panel.contentPreferredWidth
  property real contentPreferredHeight: panel.contentPreferredHeight
  readonly property bool allowAttach: panel.allowAttach

  anchors.fill: parent

  HollylandUi.HollylandPanel {
    id: panel
    anchors.fill: parent
    pluginName: root.pluginApi?.manifest?.name || "Hollyland"
    pluginDescription: root.pluginApi?.manifest?.description || ""
    state: root.mainInstance ? (root.mainInstance.state || ({})) : ({})
    summary: root.mainInstance ? (root.mainInstance.summary || ({})) : ({})
    backend: root.mainInstance ? (root.mainInstance.backend || ({})) : ({})
    updatedAt: root.mainInstance ? root.mainInstance.updatedAt : ""
    bannerText: root.mainInstance ? root.mainInstance.bannerText : ""
    bannerIsError: root.mainInstance ? root.mainInstance.bannerIsError : false
    actionBusy: root.mainInstance ? root.mainInstance.actionBusy : false
    pendingAction: root.mainInstance ? root.mainInstance.pendingAction : ""
    voiceLevelMin: root.mainInstance ? root.mainInstance.voiceLevelMin : 0
    voiceLevelMax: root.mainInstance ? root.mainInstance.voiceLevelMax : 5

    runActionFn: function(payload) {
      if (root.mainInstance) root.mainInstance.runAction(payload);
    }
    setBooleanActionFn: function(action, on, extras) {
      if (root.mainInstance) root.mainInstance.setBooleanAction(action, on, extras);
    }
    setVoiceLevelFn: function(value) {
      if (root.mainInstance) root.mainInstance.setVoiceLevel(value);
    }
    refreshStateFn: function() {
      if (root.mainInstance) root.mainInstance.refreshState();
    }

    onCloseRequested: {
      if (root.pluginApi) {
        root.pluginApi.withCurrentScreen(function(screen) { root.pluginApi.closePanel(screen); });
      }
    }
  }
}
