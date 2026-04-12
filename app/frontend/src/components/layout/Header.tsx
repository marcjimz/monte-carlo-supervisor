import { useUser } from "../../lib/user-context";
import { User } from "lucide-react";

export function Header() {
  const { user } = useUser();

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-card px-6">
      <h1 className="text-lg font-semibold">Monte Carlo Supervisor</h1>
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <User className="h-4 w-4" />
        <span>{user?.username ?? "..."}</span>
      </div>
    </header>
  );
}
