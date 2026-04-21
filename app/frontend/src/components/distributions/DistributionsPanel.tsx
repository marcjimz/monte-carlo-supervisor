import { Database } from "lucide-react";

interface Props {
  dashboardUrl?: string;
}

export function DistributionsPanel({ dashboardUrl }: Props) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <Database className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-medium">Data Explorer</h3>
      </div>
      <div
        className="border border-border rounded-lg overflow-hidden"
        style={{ height: "calc(100vh - 280px)", minHeight: "400px" }}
      >
        {dashboardUrl ? (
          <iframe
            src={dashboardUrl}
            className="w-full h-full border-0"
            title="Data Explorer"
            allow="fullscreen"
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-3">
            <Database className="h-8 w-8 opacity-40" />
            <div className="text-center">
              <p className="text-sm font-medium">
                AI/BI Dashboard not configured
              </p>
              <p className="text-xs mt-1">
                Set <code className="bg-muted px-1 rounded">DASHBOARD_ID</code> in
                app settings to embed a Lakeview dashboard for interactive data
                exploration.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
