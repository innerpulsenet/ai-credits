// IDs persist independently of display labels. New providers sort after saved ones.
function sorted(providers, saved) {
    const ids = String(saved || "").split(",").filter(id => id !== "");
    return providers.slice().sort((a, b) => {
        const ai = ids.indexOf(a.id), bi = ids.indexOf(b.id);
        if (ai !== bi) {
            if (ai < 0) return 1;
            if (bi < 0) return -1;
            return ai - bi;
        }
        return a.label.localeCompare(b.label);
    });
}

function catalog() {
    return [
        {id: "alibaba", label: "Alibaba"},
        {id: "antigravity", label: "Antigravity"},
        {id: "claude", label: "Claude"},
        {id: "codex", label: "Codex"},
        {id: "nous", label: "Nous Portal"},
        {id: "openrouter", label: "OpenRouter"},
        {id: "grok", label: "SuperGrok"},
        {id: "zai", label: "ZCode GLM"}
    ];
}
