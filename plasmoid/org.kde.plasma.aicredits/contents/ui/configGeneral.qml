pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

QQC2.ScrollView {
    id: page
    clip: true
    contentWidth: availableWidth
    QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff

    property alias cfg_statePath: statePath.text
    property alias cfg_refreshCommand: refreshCommand.text
    property alias cfg_cliPath: cliPath.text
    property alias cfg_readIntervalMs: readInterval.value
    property alias cfg_warnPct: warnPct.value
    property alias cfg_criticalPct: criticalPct.value
    property alias cfg_hideUnconfigured: hideUnconfigured.checked

    readonly property color glass: Qt.rgba(Kirigami.Theme.backgroundColor.r,
                                            Kirigami.Theme.backgroundColor.g,
                                            Kirigami.Theme.backgroundColor.b, 0.52)
    readonly property color glassRaised: Qt.rgba(Kirigami.Theme.textColor.r,
                                                  Kirigami.Theme.textColor.g,
                                                  Kirigami.Theme.textColor.b, 0.055)
    readonly property color glassHover: Qt.rgba(Kirigami.Theme.highlightColor.r,
                                                 Kirigami.Theme.highlightColor.g,
                                                 Kirigami.Theme.highlightColor.b, 0.10)
    readonly property color hairline: Qt.rgba(Kirigami.Theme.textColor.r,
                                               Kirigami.Theme.textColor.g,
                                               Kirigami.Theme.textColor.b, 0.13)
    readonly property int cardRadius: Math.round(Kirigami.Units.gridUnit * 0.65)

    component GlassField: QQC2.TextField {
        leftPadding: Kirigami.Units.largeSpacing
        rightPadding: Kirigami.Units.largeSpacing
        implicitHeight: Kirigami.Units.gridUnit * 2.25
        background: Rectangle {
            radius: Math.round(Kirigami.Units.gridUnit * 0.45)
            color: parent.activeFocus ? page.glassHover : page.glass
            border.width: parent.activeFocus ? 2 : 1
            border.color: parent.activeFocus ? Kirigami.Theme.highlightColor : page.hairline
            Behavior on color { ColorAnimation { duration: Kirigami.Units.shortDuration } }
        }
    }

    ColumnLayout {
        width: page.availableWidth
        spacing: Kirigami.Units.largeSpacing

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: generalIntro.implicitHeight + Kirigami.Units.gridUnit * 2
            radius: page.cardRadius
            color: page.glassRaised
            border.width: 1
            border.color: page.hairline

            Rectangle {
                anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
                width: Math.round(Kirigami.Units.smallSpacing * 0.65)
                radius: parent.radius
                color: Kirigami.Theme.highlightColor
                opacity: 0.8
            }

            RowLayout {
                id: generalIntro
                anchors {
                    fill: parent
                    margins: Kirigami.Units.gridUnit
                    leftMargin: Kirigami.Units.gridUnit * 1.25
                }
                spacing: Kirigami.Units.largeSpacing

                Rectangle {
                    Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                    Layout.preferredHeight: width
                    radius: width / 2
                    color: page.glassHover
                    Kirigami.Icon {
                        anchors.centerIn: parent
                        width: Kirigami.Units.iconSizes.smallMedium
                        height: width
                        source: "settings-configure"
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Heading { text: i18n("General settings"); level: 2 }
                    QQC2.Label {
                        Layout.fillWidth: true
                        text: i18n("Choose how the popup refreshes, where it reads data, and when usage needs your attention.")
                        wrapMode: Text.WordWrap
                        color: Kirigami.Theme.disabledTextColor
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: sourceContent.implicitHeight + Kirigami.Units.gridUnit * 1.5
            radius: page.cardRadius
            color: sourceHover.hovered ? page.glassHover : page.glassRaised
            border.width: 1
            border.color: page.hairline
            Behavior on color { ColorAnimation { duration: Kirigami.Units.shortDuration } }
            HoverHandler { id: sourceHover }

            ColumnLayout {
                id: sourceContent
                anchors { fill: parent; margins: Math.round(Kirigami.Units.gridUnit * 0.75) }
                spacing: Kirigami.Units.largeSpacing

                RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.Icon {
                        source: "folder-sync"
                        Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                        Layout.preferredHeight: width
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        QQC2.Label { text: i18n("Data source"); font.weight: Font.DemiBold }
                        QQC2.Label {
                            text: i18n("Paths may be absolute or relative to your home directory.")
                            color: Kirigami.Theme.disabledTextColor
                            font: Kirigami.Theme.smallFont
                        }
                    }
                }

                Kirigami.FormLayout {
                    Layout.fillWidth: true
                    GlassField {
                        id: statePath
                        Kirigami.FormData.label: i18n("Snapshot file:")
                        Layout.fillWidth: true
                    }
                    GlassField {
                        id: refreshCommand
                        Kirigami.FormData.label: i18n("Custom refresh command:")
                        placeholderText: i18n("Leave blank for a forced refresh")
                        Layout.fillWidth: true
                    }
                    GlassField {
                        id: cliPath
                        Kirigami.FormData.label: i18n("AI Credits command:")
                        Layout.fillWidth: true
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: behaviorContent.implicitHeight + Kirigami.Units.gridUnit * 1.5
            radius: page.cardRadius
            color: behaviorHover.hovered ? page.glassHover : page.glassRaised
            border.width: 1
            border.color: page.hairline
            Behavior on color { ColorAnimation { duration: Kirigami.Units.shortDuration } }
            HoverHandler { id: behaviorHover }

            ColumnLayout {
                id: behaviorContent
                anchors { fill: parent; margins: Math.round(Kirigami.Units.gridUnit * 0.75) }
                spacing: Kirigami.Units.largeSpacing

                RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.Icon {
                        source: "speedometer"
                        Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                        Layout.preferredHeight: width
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        QQC2.Label { text: i18n("Display and alerts"); font.weight: Font.DemiBold }
                        QQC2.Label {
                            text: i18n("Tune freshness and the points where meters change color.")
                            color: Kirigami.Theme.disabledTextColor
                            font: Kirigami.Theme.smallFont
                        }
                    }
                }

                Kirigami.FormLayout {
                    Layout.fillWidth: true
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
            }
        }

        Item { Layout.preferredHeight: Kirigami.Units.smallSpacing }
    }
}
