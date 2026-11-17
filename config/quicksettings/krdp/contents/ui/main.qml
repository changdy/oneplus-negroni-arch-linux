// SPDX-License-Identifier: MIT
import QtQuick
import org.kde.plasma.plasma5support as Plasma5Support
import org.kde.plasma.private.mobileshell.quicksettingsplugin as QS

QS.QuickSetting {
    id: root
    readonly property string unit: "app-org.kde.krdpserver.service"
    readonly property string systemctl: "/usr/bin/systemctl --user "
    readonly property string statusCommand: systemctl + "show --property=ActiveState --value " + unit
    readonly property bool chinese: Qt.locale().name === "zh_CN"
    property string serviceState: ""
    property string runningCommand: ""

    text: chinese ? "远程桌面" : i18n("Remote Desktop")
    icon: "preferences-system-network-remote"
    enabled: serviceState === "active"
    settingsCommand: "kcmshell6 kcm_krdpserver"
    status: {
        switch (serviceState) {
        case "active": return "USB · 10.55.0.1"
        case "inactive": return chinese ? "已关闭" : i18n("Off")
        case "activating": return chinese ? "正在开启…" : i18n("Starting…")
        case "deactivating": return chinese ? "正在关闭…" : i18n("Stopping…")
        case "failed": return chinese ? "启动失败" : i18n("Failed to start")
        case "error": return chinese ? "操作失败" : i18n("Operation failed")
        default: return chinese ? "正在检查…" : i18n("Checking…")
        }
    }

    function run(command) {
        runningCommand = command
        commands.connectSource(command)
    }

    function toggle() {
        if (runningCommand !== "" || serviceState === "" ||
                serviceState === "activating" || serviceState === "deactivating")
            return
        const action = enabled ? "stop " : "start "
        run(systemctl + action + unit + " && " + statusCommand)
    }

    Timer {
        interval: 10000
        repeat: true
        running: true
        triggeredOnStart: true
        onTriggered: {
            if (root.runningCommand === "")
                root.run(root.statusCommand)
        }
    }

    Plasma5Support.DataSource {
        id: commands
        engine: "executable"
        onNewData: function(sourceName, data) {
            if (sourceName !== root.runningCommand || data["exit code"] === undefined)
                return
            disconnectSource(sourceName)
            root.serviceState = data["exit code"] === 0 ? String(data["stdout"]).trim() : "error"
            root.runningCommand = ""
        }
    }
}
