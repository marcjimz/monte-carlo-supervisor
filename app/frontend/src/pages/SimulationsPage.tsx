import { SimulationBrowser } from "../components/simulations/SimulationBrowser";

export function SimulationsPage() {
  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold">Simulations</h2>
        <p className="text-muted-foreground text-sm mt-1">
          Browse all Monte Carlo simulation runs
        </p>
      </div>
      <SimulationBrowser />
    </div>
  );
}
