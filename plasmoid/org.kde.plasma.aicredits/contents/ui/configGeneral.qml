import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.FormLayout {
    id: page

    property alias cfg_statePath: statePath.text
    property alias cfg_refreshCommand: refreshCommand.text
    property alias cfg_readIntervalMs: readInterval.value
    property alias cfg_warnPct: warnPct.value
    property alias cfg_criticalPct: criticalPct.value
    property alias cfg_hideUnconfigured: hideUnconfigured.checked

    QQC2.TextField {
        id: statePath
        Kirigami.FormData.label: i18n("Snapshot file:")
        implicitWidth: Kirigami.Units.gridUnit * 22
    }

    QQC2.Label {
        text: i18n("Relative paths are resolved against your home directory.")
        font: Kirigami.Theme.smallFont
        opacity: 0.7
    }

    QQC2.TextField {
        id: refreshCommand
        Kirigami.FormData.label: i18n("Refresh command:")
        implicitWidth: Kirigami.Units.gridUnit * 22
    }

    Item { Kirigami.FormData.isSection: true }

    QQC2.SpinBox {
        id: readInterval
        Kirigami.FormData.label: i18n("Re-read snapshot every:")
        from: 5000
        to: 600000
        stepSize: 5000
        textFromValue: value => i18n("%1 seconds", Math.round(value / 1000))
        valueFromText: text => parseInt(text) * 1000
    }

    QQC2.SpinBox {
        id: warnPct
        Kirigami.FormData.label: i18n("Amber above:")
        from: 1
        to: 100
        textFromValue: value => value + "%"
    }

    QQC2.SpinBox {
        id: criticalPct
        Kirigami.FormData.label: i18n("Red above:")
        from: 1
        to: 100
        textFromValue: value => value + "%"
    }

    QQC2.CheckBox {
        id: hideUnconfigured
        Kirigami.FormData.label: i18n("Providers:")
        text: i18n("Hide providers that need setup")
    }
}
