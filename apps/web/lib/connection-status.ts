export type ServerConnectionStatus = "connected" | "disconnected";

const CONNECTION_STATUS_PRESENTATION = {
  connected: {
    label: "Connected",
    dotClassName: "bg-emerald-400",
  },
  disconnected: {
    label: "Disconnected",
    dotClassName: "bg-orange-400",
  },
} as const satisfies Record<ServerConnectionStatus, {
  label: string;
  dotClassName: string;
}>;

export function connectionStatusPresentation(status: ServerConnectionStatus) {
  return CONNECTION_STATUS_PRESENTATION[status];
}
