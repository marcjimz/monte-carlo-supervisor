import { MessageSquare } from "lucide-react";

interface Props {
  genieUrl?: string;
}

export function GeniePanel({ genieUrl }: Props) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <MessageSquare className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-medium">Chat with your Data</h3>
      </div>
      <div
        className="border border-border rounded-lg overflow-hidden"
        style={{ height: "calc(100vh - 280px)", minHeight: "400px" }}
      >
        {genieUrl ? (
          <iframe
            src={genieUrl}
            className="w-full h-full border-0"
            title="Chat with your Data"
            allow="clipboard-write"
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-3">
            <MessageSquare className="h-8 w-8 opacity-40" />
            <div className="text-center">
              <p className="text-sm font-medium">
                Genie Space not configured
              </p>
              <p className="text-xs mt-1">
                Set <code className="bg-muted px-1 rounded">GENIE_SPACE_ID</code> in
                app settings to embed a Genie room for interactive data chat.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
