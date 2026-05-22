.pragma library

var TX1_ACCENT = "#7667d9";
var TX2_ACCENT = "#d1a645";
var TX3_ACCENT = "#55b4d4";
var TX4_ACCENT = "#86b300";
var FALLBACK_ACCENT = "#ff8f40";

function accentColorForTx(txId) {
  const normalized = String(txId || "").toLowerCase();
  if (normalized === "tx1")
    return TX1_ACCENT;
  if (normalized === "tx2")
    return TX2_ACCENT;
  if (normalized === "tx3")
    return TX3_ACCENT;
  if (normalized === "tx4")
    return TX4_ACCENT;
  return FALLBACK_ACCENT;
}
