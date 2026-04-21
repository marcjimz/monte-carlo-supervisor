import { useUser } from "../../lib/user-context";
import { getInitials } from "../../lib/utils";

export function Header() {
  const { user } = useUser();
  const initials = user?.email ? getInitials(user.email) : "?";

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-primary px-6">
      <div />
      <div className="flex items-center gap-2.5 text-sm text-primary-foreground/90">
        <span>{user?.username ?? "..."}</span>
        <div className="w-8 h-8 rounded-full bg-primary-foreground/20 flex items-center justify-center">
          <span className="text-xs font-bold text-primary-foreground">
            {initials}
          </span>
        </div>
      </div>
    </header>
  );
}
