pragma ComponentBehavior: Bound

import QtQuick
import QtCore
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasma5support as Plasma5Support

QQC2.ScrollView {
    id: page
    clip: true
    contentWidth: availableWidth
    QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff

    readonly property string homeDir:
        String(StandardPaths.standardLocations(StandardPaths.HomeLocation)[0])
            .replace(/^file:\/\//, "")
    property string cfg_cliPath: "Documents/ai-credits/bin/aicredits"
    readonly property string cliPath: page.cfg_cliPath.startsWith("/")
                                      ? page.cfg_cliPath
                                      : page.homeDir + "/" + page.cfg_cliPath
    readonly property string readCommand: page.quote(page.cliPath) + " config get providers"
    property bool busy: false
    property string resultText: ""

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

    component GlassCombo: QQC2.ComboBox {
        id: combo
        implicitHeight: Kirigami.Units.gridUnit * 2.25
        leftPadding: Kirigami.Units.largeSpacing
        rightPadding: Kirigami.Units.gridUnit * 2.2

        contentItem: QQC2.Label {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: combo.leftPadding
            anchors.rightMargin: combo.rightPadding
            text: combo.displayText
            font: combo.font
            color: Kirigami.Theme.textColor
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }

        indicator: Kirigami.Icon {
            anchors.right: combo.right
            anchors.rightMargin: Kirigami.Units.largeSpacing
            anchors.verticalCenter: combo.verticalCenter
            implicitWidth: Kirigami.Units.iconSizes.small
            implicitHeight: implicitWidth
            source: "arrow-down"
            color: combo.hovered ? Kirigami.Theme.highlightColor : Kirigami.Theme.disabledTextColor
        }

        background: Rectangle {
            radius: Math.round(Kirigami.Units.gridUnit * 0.45)
            color: combo.activeFocus ? page.glassHover : page.glass
            border.width: combo.activeFocus ? 2 : 1
            border.color: combo.activeFocus ? Kirigami.Theme.highlightColor : page.hairline
            Behavior on color { ColorAnimation { duration: Kirigami.Units.shortDuration } }
        }

        delegate: QQC2.ItemDelegate {
            id: itemDel
            width: combo.width
            contentItem: QQC2.Label {
                text: modelData
                color: itemDel.highlighted ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor
                font: combo.font
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
            }
            highlighted: combo.highlightedIndex === index
            background: Rectangle {
                color: itemDel.highlighted ? Kirigami.Theme.highlightColor : "transparent"
                radius: 4
            }
        }

        popup: QQC2.Popup {
            y: combo.height + 2
            width: combo.width
            implicitHeight: contentItem.implicitHeight + 8
            padding: 4

            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: combo.popup.visible ? combo.delegateModel : null
                currentIndex: combo.highlightedIndex
                QQC2.ScrollIndicator.vertical: QQC2.ScrollIndicator {}
            }

            background: Rectangle {
                radius: Math.round(Kirigami.Units.gridUnit * 0.45)
                color: Kirigami.Theme.backgroundColor
                border.width: 1
                border.color: page.hairline
            }
        }
    }

    property int editRevision: 0

    function providerMeta(id) {
        switch (id) {
        case "codex": return { glyph: "CX", color: "#10a37f" };
        case "claude": return { glyph: "CL", color: "#d97706" };
        case "grok": return { glyph: "GK", color: "#9333ea" };
        case "zai": return { glyph: "ZA", color: "#06b6d4" };
        case "alibaba": return { glyph: "AL", color: "#f97316" };
        case "nous": return { glyph: "NP", color: "#3b82f6" };
        case "antigravity": return { glyph: "AG", color: "#ec4899" };
        default: return { glyph: id.slice(0, 2).toUpperCase(), color: Kirigami.Theme.highlightColor };
        }
    }

    function computeMonthlyEquivalent(costStr, cadence) {
        const cost = parseFloat(costStr) || 0;
        if (cost <= 0)
            return 0;
        const cad = (cadence || "monthly").toLowerCase();
        if (cad === "daily")
            return (cost * 365) / 12;
        if (cad === "weekly")
            return (cost * 52) / 12;
        if (cad === "quarterly")
            return cost / 3;
        if (cad === "annual" || cad === "yearly")
            return cost / 12;
        return cost;
    }

    readonly property real liveTotalMonthly: {
        const rev = page.editRevision;
        let sum = 0;
        for (let i = 0; i < subscriptions.count; ++i) {
            const item = subscriptions.get(i);
            if (item.date && item.date.trim() !== "") {
                sum += page.computeMonthlyEquivalent(item.cost, item.cadence);
            }
        }
        return sum;
    }

    readonly property int liveActiveCount: {
        const rev = page.editRevision;
        let count = 0;
        for (let i = 0; i < subscriptions.count; ++i) {
            const item = subscriptions.get(i);
            if (item.date && item.date.trim() !== "") {
                count++;
            }
        }
        return count;
    }

    function quote(value) {
        return "'" + String(value).replace(/'/g, "'\\''") + "'";
    }

    function setEditor(providerId, data) {
        const renewal = (data && data.renewal) || ({});
        for (let i = 0; i < subscriptions.count; ++i) {
            if (subscriptions.get(i).providerId !== providerId)
                continue;
            subscriptions.setProperty(i, "date", renewal.date || "");
            subscriptions.setProperty(i, "cost", renewal.cost_usd !== undefined
                                      ? String(renewal.cost_usd) : "");
            subscriptions.setProperty(i, "cadence", renewal.cadence || "monthly");
            break;
        }
    }

    function loadValues(text) {
        try {
            const providers = JSON.parse(text);
            for (let i = 0; i < subscriptions.count; ++i) {
                const id = subscriptions.get(i).providerId;
                page.setEditor(id, providers[id]);
            }
            page.resultText = "";
            page.editRevision++;
        } catch (error) {
            page.resultText = i18n("Could not read the subscription configuration.");
        }
    }

    function saveValues() {
        const commands = [];
        for (let i = 0; i < subscriptions.count; ++i) {
            const item = subscriptions.get(i);
            const prefix = "providers." + item.providerId + ".renewal.";
            const values = {"date": item.date.trim(), "cost_usd": item.cost.trim(),
                            "cadence": item.cadence};
            for (const key of ["date", "cost_usd", "cadence"]) {
                const verb = values[key] === "" ? "unset" : "set";
                let command = page.quote(page.cliPath) + " config " + verb + " " + prefix + key;
                if (verb === "set")
                    command += " " + page.quote(values[key]);
                commands.push(command);
            }
        }
        commands.push("systemctl --user start aicredits.service");
        page.busy = true;
        page.resultText = i18n("Saving…");
        writer.connectSource(commands.join(" && "));
    }

    ListModel {
        id: subscriptions
        ListElement { providerId: "codex"; label: "Codex"; date: ""; cost: ""; cadence: "monthly" }
        ListElement { providerId: "grok"; label: "SuperGrok"; date: ""; cost: ""; cadence: "monthly" }
        ListElement { providerId: "zai"; label: "ZCode GLM"; date: ""; cost: ""; cadence: "monthly" }
        ListElement { providerId: "claude"; label: "Claude"; date: ""; cost: ""; cadence: "monthly" }
        ListElement { providerId: "alibaba"; label: "Alibaba"; date: ""; cost: ""; cadence: "monthly" }
        ListElement { providerId: "nous"; label: "Nous Portal"; date: ""; cost: ""; cadence: "monthly" }
        ListElement { providerId: "antigravity"; label: "Antigravity"; date: ""; cost: ""; cadence: "monthly" }
    }

    Plasma5Support.DataSource {
        id: reader
        engine: "executable"
        connectedSources: [page.readCommand]
        interval: 0
        onNewData: function(source, data) {
            disconnectSource(source);
            if (data["exit code"] === 0)
                page.loadValues(data["stdout"]);
            else
                page.resultText = i18n("Could not run %1", page.cliPath);
        }
    }

    Plasma5Support.DataSource {
        id: writer
        engine: "executable"
        connectedSources: []
        interval: 0
        onNewData: function(source, data) {
            disconnectSource(source);
            page.busy = false;
            page.resultText = data["exit code"] === 0
                              ? i18n("Subscriptions saved. The popup will update shortly.")
                              : i18n("Could not save subscriptions.");
        }
    }

    ColumnLayout {
        width: page.availableWidth
        spacing: Kirigami.Units.largeSpacing

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: introContent.implicitHeight + Kirigami.Units.gridUnit * 1.6
            radius: page.cardRadius
            color: page.glassRaised
            border.width: 1
            border.color: page.hairline

            RowLayout {
                id: introContent
                anchors {
                    fill: parent
                    margins: Kirigami.Units.gridUnit
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
                        source: "view-calendar"
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Heading {
                        text: i18n("Subscription ledger")
                        level: 2
                    }
                    QQC2.Label {
                        Layout.fillWidth: true
                        text: i18n("Track recurring plans and renewals. OpenRouter is excluded (prepaid credits).")
                        wrapMode: Text.WordWrap
                        color: Kirigami.Theme.disabledTextColor
                    }
                }

                // Live Monthly Spend Stat Box
                Rectangle {
                    Layout.preferredWidth: Math.round(Kirigami.Units.gridUnit * 9.5)
                    Layout.preferredHeight: Math.round(Kirigami.Units.gridUnit * 3.4)
                    radius: page.cardRadius
                    color: page.glass
                    border.width: 1
                    border.color: Qt.rgba(Kirigami.Theme.highlightColor.r,
                                          Kirigami.Theme.highlightColor.g,
                                          Kirigami.Theme.highlightColor.b, 0.25)

                    ColumnLayout {
                        anchors.centerIn: parent
                        spacing: 1

                        QQC2.Label {
                            text: i18n("ESTIMATED MONTHLY")
                            font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.78)
                            font.letterSpacing: 0.8
                            color: Kirigami.Theme.disabledTextColor
                            Layout.alignment: Qt.AlignHCenter
                        }

                        QQC2.Label {
                            text: "$" + page.liveTotalMonthly.toFixed(2) + i18n(" / mo")
                            font.pixelSize: Math.round(Kirigami.Theme.defaultFont.pixelSize * 1.25)
                            font.weight: Font.Bold
                            color: Kirigami.Theme.highlightColor
                            Layout.alignment: Qt.AlignHCenter
                        }

                        QQC2.Label {
                            text: i18n("%1 of %2 Active", page.liveActiveCount, subscriptions.count)
                            font: Kirigami.Theme.smallFont
                            color: page.liveActiveCount > 0 ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                            Layout.alignment: Qt.AlignHCenter
                        }
                    }
                }
            }
        }

        Repeater {
            model: subscriptions

            delegate: Rectangle {
                id: editor
                required property int index
                required property string providerId
                required property string label
                required property string date
                required property string cost
                required property string cadence
                Layout.fillWidth: true
                Layout.preferredHeight: fields.implicitHeight + Kirigami.Units.gridUnit * 1.5
                radius: page.cardRadius
                color: cardHover.hovered ? page.glassHover : page.glassRaised
                border.width: 1
                border.color: editor.date !== "" ? Qt.rgba(Kirigami.Theme.highlightColor.r,
                                                             Kirigami.Theme.highlightColor.g,
                                                             Kirigami.Theme.highlightColor.b, 0.35)
                                                : page.hairline
                Behavior on color { ColorAnimation { duration: Kirigami.Units.shortDuration } }

                HoverHandler { id: cardHover }

                RowLayout {
                    id: fields
                    anchors { fill: parent; margins: Math.round(Kirigami.Units.gridUnit * 0.75) }
                    spacing: Kirigami.Units.largeSpacing

                    readonly property var meta: page.providerMeta(editor.providerId)

                    RowLayout {
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 8.5
                        spacing: Kirigami.Units.largeSpacing

                        Rectangle {
                            Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                            Layout.preferredHeight: width
                            radius: width / 2
                            color: editor.date !== "" ? Qt.rgba(fields.meta.color.r, fields.meta.color.g, fields.meta.color.b, 0.2)
                                                      : page.glass
                            border.width: 1
                            border.color: editor.date !== "" ? fields.meta.color : page.hairline

                            QQC2.Label {
                                anchors.centerIn: parent
                                text: fields.meta.glyph
                                color: editor.date !== "" ? fields.meta.color : Kirigami.Theme.disabledTextColor
                                font.weight: Font.Bold
                                font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.95)
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            QQC2.Label {
                                Layout.fillWidth: true
                                text: editor.label
                                font.weight: Font.DemiBold
                                font.pixelSize: Math.round(Kirigami.Theme.defaultFont.pixelSize * 1.05)
                                elide: Text.ElideRight
                            }
                            Rectangle {
                                implicitHeight: Math.round(statusLabel.implicitHeight + 2)
                                implicitWidth: Math.round(statusLabel.implicitWidth + 8)
                                radius: 4
                                color: editor.date !== "" ? Qt.rgba(Kirigami.Theme.positiveTextColor.r,
                                                                    Kirigami.Theme.positiveTextColor.g,
                                                                    Kirigami.Theme.positiveTextColor.b, 0.15)
                                                          : page.glass
                                border.width: 1
                                border.color: editor.date !== "" ? Qt.rgba(Kirigami.Theme.positiveTextColor.r,
                                                                           Kirigami.Theme.positiveTextColor.g,
                                                                           Kirigami.Theme.positiveTextColor.b, 0.3)
                                                                 : page.hairline

                                QQC2.Label {
                                    id: statusLabel
                                    anchors.centerIn: parent
                                    text: editor.date !== "" ? i18n("ACTIVE") : i18n("INACTIVE")
                                    color: editor.date !== "" ? Kirigami.Theme.positiveTextColor
                                                              : Kirigami.Theme.disabledTextColor
                                    font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.75)
                                    font.letterSpacing: 0.8
                                    font.weight: Font.DemiBold
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        spacing: 2
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 8
                        QQC2.Label {
                            text: i18n("NEXT RENEWAL")
                            color: Kirigami.Theme.disabledTextColor
                            font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.82)
                            font.letterSpacing: 0.8
                        }
                        GlassField {
                            text: editor.date
                            placeholderText: i18n("YYYY-MM-DD")
                            Accessible.name: i18n("%1 renewal date", editor.label)
                            Layout.fillWidth: true
                            validator: RegularExpressionValidator {
                                regularExpression: /(^$)|(^\d{4}-\d{2}-\d{2}$)/
                            }
                            onTextEdited: {
                                subscriptions.setProperty(editor.index, "date", text);
                                page.editRevision++;
                            }
                        }
                    }

                    ColumnLayout {
                        spacing: 2
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 6.5
                        RowLayout {
                            Layout.fillWidth: true
                            QQC2.Label {
                                text: i18n("PRICE · USD")
                                color: Kirigami.Theme.disabledTextColor
                                font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.82)
                                font.letterSpacing: 0.8
                            }
                            Item { Layout.fillWidth: true }
                            QQC2.Label {
                                readonly property real monthlyEq: page.computeMonthlyEquivalent(editor.cost, editor.cadence)
                                visible: monthlyEq > 0 && editor.cadence !== "monthly"
                                text: "≈ $" + monthlyEq.toFixed(2) + "/mo"
                                color: Kirigami.Theme.highlightColor
                                font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.78)
                            }
                        }
                        GlassField {
                            text: editor.cost
                            placeholderText: "0.00"
                            Accessible.name: i18n("%1 subscription price", editor.label)
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                            Layout.fillWidth: true
                            validator: DoubleValidator { bottom: 0; decimals: 2 }
                            onTextEdited: {
                                subscriptions.setProperty(editor.index, "cost", text);
                                page.editRevision++;
                            }
                        }
                    }

                    ColumnLayout {
                        spacing: 2
                        Layout.fillWidth: true
                        QQC2.Label {
                            text: i18n("BILLING CYCLE")
                            color: Kirigami.Theme.disabledTextColor
                            font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.82)
                            font.letterSpacing: 0.8
                        }
                        GlassCombo {
                            id: cadenceBox
                            readonly property var cadenceValues: ["monthly", "quarterly", "annual", "weekly", "daily"]
                            model: [i18n("Monthly"), i18n("Quarterly"), i18n("Annual"), i18n("Weekly"), i18n("Daily")]
                            currentIndex: {
                                const idx = cadenceValues.indexOf(editor.cadence);
                                return idx >= 0 ? idx : 0;
                            }
                            Accessible.name: i18n("%1 billing cycle", editor.label)
                            Layout.fillWidth: true
                            onActivated: {
                                subscriptions.setProperty(editor.index, "cadence",
                                                          cadenceValues[currentIndex]);
                                page.editRevision++;
                            }
                        }
                    }
                }
            }
        }

        Kirigami.InlineMessage {
            visible: page.resultText !== ""
            text: page.resultText
            type: Kirigami.MessageType.Information
            Layout.fillWidth: true
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: actionRow.implicitHeight + Kirigami.Units.gridUnit * 1.25
            radius: page.cardRadius
            color: page.glassRaised
            border.width: 1
            border.color: page.hairline

            RowLayout {
                id: actionRow
                anchors { fill: parent; margins: Math.round(Kirigami.Units.gridUnit * 0.625) }
                spacing: Kirigami.Units.largeSpacing

                Kirigami.Icon {
                    source: "document-save"
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                    Layout.preferredHeight: width
                }
                QQC2.Label {
                    Layout.fillWidth: true
                    text: i18n("Changes update the popup and monthly total immediately.")
                    color: Kirigami.Theme.disabledTextColor
                }
                QQC2.Button {
                    text: page.busy ? i18n("Saving…") : i18n("Save subscriptions")
                    icon.name: page.busy ? "view-refresh" : "document-save"
                    highlighted: true
                    enabled: !page.busy
                    onClicked: page.saveValues()
                }
            }
        }

        Item { Layout.preferredHeight: Kirigami.Units.smallSpacing }
    }
}
