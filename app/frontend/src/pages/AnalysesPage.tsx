import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { api } from "../lib/api";
import type { Analysis } from "../lib/types";
import { formatDate } from "../lib/utils";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Card, CardDescription, CardTitle } from "../components/ui/card";
import { Spinner } from "../components/ui/spinner";
import { CreateAnalysisDialog } from "../components/analyses/CreateAnalysisDialog";

export function AnalysesPage() {
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  const fetchAnalyses = () => {
    setLoading(true);
    api
      .get<{ analyses: Analysis[] }>("/analyses")
      .then((data) => setAnalyses(data.analyses))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(fetchAnalyses, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">Analyses</h2>
          <p className="text-muted-foreground text-sm mt-1">
            Create and manage Monte Carlo simulation analyses
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4" />
          New Analysis
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Spinner className="h-6 w-6" />
        </div>
      ) : analyses.length === 0 ? (
        <Card className="text-center py-12">
          <p className="text-muted-foreground">No analyses yet.</p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => setShowCreate(true)}
          >
            Create your first analysis
          </Button>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {analyses.map((a) => (
            <Link key={a.id} to={`/analyses/${a.id}`}>
              <Card className="hover:border-primary/50 transition-colors cursor-pointer">
                <div className="flex items-start justify-between mb-2">
                  <CardTitle className="text-base">{a.name}</CardTitle>
                  <Badge
                    variant={a.status === "published" ? "success" : "secondary"}
                  >
                    {a.status}
                  </Badge>
                </div>
                {a.description && (
                  <CardDescription className="line-clamp-2">
                    {a.description}
                  </CardDescription>
                )}
                <div className="mt-3 flex items-center gap-3 text-xs text-muted-foreground">
                  <span>{a.owner_email}</span>
                  <span>{formatDate(a.created_at)}</span>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}

      <CreateAnalysisDialog
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreate={() => {
          setShowCreate(false);
          fetchAnalyses();
        }}
      />
    </div>
  );
}
