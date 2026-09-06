import QtQuick
import org.kde.plasma.configuration

ConfigModel {
    ConfigCategory {
        name: i18n("General")
        icon: "configure"
        source: "configGeneral.qml"
    }
    ConfigCategory {
        name: i18n("Provider order")
        icon: "view-sort-ascending"
        source: "configProviderOrder.qml"
    }
    ConfigCategory {
        name: i18n("Subscriptions")
        icon: "view-calendar"
        source: "configSubscriptions.qml"
    }
}
