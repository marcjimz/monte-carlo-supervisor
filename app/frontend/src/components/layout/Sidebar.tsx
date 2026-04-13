import { NavLink } from "react-router-dom";
import { BarChart3, FlaskConical } from "lucide-react";
import { cn } from "../../lib/utils";

const NAV_ITEMS = [
  { to: "/analyses", label: "Analyses", icon: BarChart3 },
  { to: "/simulations", label: "Simulations", icon: FlaskConical },
];

export function Sidebar() {
  return (
    <aside className="flex w-56 flex-col border-r border-primary bg-card">
      <div className="flex h-14 items-center gap-2 px-4 bg-primary border-b border-border">
        <img src="/logo.png" alt="Intermountain Health" className="h-7" />
        <span className="font-bold text-sm leading-tight text-primary-foreground">
          Accelerate
        </span>
      </div>
      <nav className="flex-1 p-3 space-y-1">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )
            }
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="p-3 border-t border-border text-[10px] text-muted-foreground">
        Powered by Intermountain Health
      </div>
    </aside>
  );
}
