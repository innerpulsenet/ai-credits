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
        {id: "alibaba", label: "Alibaba", glyph: "AL", color: "#f97316"},
        {id: "antigravity", label: "Antigravity", glyph: "AG", color: "#ec4899"},
        {id: "claude", label: "Claude", glyph: "CL", color: "#d97706"},
        {id: "codex", label: "Codex", glyph: "CX", color: "#10a37f"},
        {id: "nous", label: "Nous Portal", glyph: "NP", color: "#3b82f6"},
        {id: "openrouter", label: "OpenRouter", glyph: "OR", color: "#6366f1"},
        {id: "grok", label: "SuperGrok", glyph: "GK", color: "#9333ea"},
        {id: "zai", label: "ZCode GLM", glyph: "ZA", color: "#06b6d4"}
    ];
}
