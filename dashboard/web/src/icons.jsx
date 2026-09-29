import React from "react";
import ForumOutlined from "@mui/icons-material/ForumOutlined";
import QueryStats from "@mui/icons-material/QueryStats";
import CalendarMonth from "@mui/icons-material/CalendarMonth";
import Straighten from "@mui/icons-material/Straighten";
import EditNote from "@mui/icons-material/EditNote";
import ManageSearch from "@mui/icons-material/ManageSearch";
import CurrencyExchange from "@mui/icons-material/CurrencyExchange";
import LocalHospital from "@mui/icons-material/LocalHospital";
import Storage from "@mui/icons-material/Storage";
import SmartToyOutlined from "@mui/icons-material/SmartToyOutlined";
import Hub from "@mui/icons-material/Hub";
import LocalFlorist from "@mui/icons-material/LocalFlorist";
import Spa from "@mui/icons-material/Spa";
import TravelExplore from "@mui/icons-material/TravelExplore";
import Construction from "@mui/icons-material/Construction";
import HowToReg from "@mui/icons-material/HowToReg";
import CheckCircle from "@mui/icons-material/CheckCircle";
import Insights from "@mui/icons-material/Insights";
import Lock from "@mui/icons-material/Lock";

// One icon per skill; agents are matched by category first, then by words in their slug.
const BY_CATEGORY = {
  sql: LocalHospital, stats: QueryStats, dates: CalendarMonth, units: Straighten,
  writing: EditNote, extraction: ManageSearch, currency: CurrencyExchange,
};
const BY_WORD = [
  ["generalist", ForumOutlined], ["hospital", LocalHospital], ["sql", Storage], ["stats", QueryStats],
  ["date", CalendarMonth], ["unit", Straighten], ["writ", EditNote], ["extract", ManageSearch], ["currency", CurrencyExchange],
];

export function agentIcon(slug, category) {
  if (category && BY_CATEGORY[category]) return BY_CATEGORY[category];
  const s = String(slug || "");
  return (BY_WORD.find(([w]) => s.includes(w)) || [null, SmartToyOutlined])[1];
}

export const CATEGORY_ICON = { dates: CalendarMonth, sql: Storage, stats: QueryStats, units: Straighten };

export const NOW_ICON = {
  idle: Spa, gap: TravelExplore, building: Construction, approval: HowToReg,
  joined: LocalFlorist, final: CheckCircle, proof: Insights,
};

export { Hub, LocalFlorist, Lock };

// An MUI icon placed inside our own SVG, centred on (x, y).
export function SvgGlyph({ Icon, x = 0, y = 0, size = 20, color = "currentColor" }) {
  return <Icon x={x - size / 2} y={y - size / 2} width={size} height={size} style={{ fontSize: size, color }} />;
}
