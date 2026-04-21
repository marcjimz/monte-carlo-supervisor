import { useState } from "react";
import { SimulationBrowser } from "../components/simulations/SimulationBrowser";
import { SimulationBuilder } from "../components/simulations/SimulationBuilder";

export function SimulationsPage() {
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold">Simulations</h2>
        <p className="text-muted-foreground text-sm mt-1">
          Build and browse Monte Carlo simulation runs
        </p>
      </div>
      <SimulationBuilder onTriggered={() => setRefreshKey((k) => k + 1)} />
      <SimulationBrowser key={refreshKey} />
    </div>
  );
}
