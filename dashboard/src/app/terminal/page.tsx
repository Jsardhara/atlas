import { MasterTerminal } from "../../components/terminal/MasterTerminal";

export default function TerminalPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-white">Master Control Terminal</h1>
        <p className="text-gray-400 text-sm mt-1">
          Talk to any agent directly or use{" "}
          <span className="font-mono text-violet-400">@oracle</span>,{" "}
          <span className="font-mono text-violet-400">@guardian</span>, etc. to route to a specific agent.
          The live feed shows every decision happening right now.
        </p>
      </div>
      <MasterTerminal />
    </div>
  );
}
