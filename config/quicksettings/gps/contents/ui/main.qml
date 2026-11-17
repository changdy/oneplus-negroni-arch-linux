// SPDX-License-Identifier: MIT
import QtQuick
import org.kde.plasma.plasma5support as Plasma5Support
import org.kde.plasma.private.mobileshell as MobileShell
import org.kde.plasma.private.mobileshell.quicksettingsplugin as QS

QS.QuickSetting {
    id: root
    property string deviceState: "unknown"

    text: i18n("GPS")
    icon: "find-location"
    status: deviceState === "on" ? i18n("On") : deviceState === "off" ? i18n("Off") : i18n("Unavailable")
    enabled: deviceState === "on"
    available: deviceState !== "unavailable"

    function toggle() {
        MobileShell.ShellUtil.executeCommand("pkexec /usr/local/libexec/negroni-hardware-control gps toggle")
    }

    Plasma5Support.DataSource {
        engine: "executable"
        connectedSources: ["/usr/local/libexec/negroni-hardware-control gps status"]
        interval: 10000
        onNewData: function(sourceName, data) {
            root.deviceState = String(data["stdout"]).trim()
        }
    }
}
