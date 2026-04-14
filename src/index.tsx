import { definePlugin, ServerAPI, staticClasses, LifetimeNotification } from "decky-frontend-lib";
import { Toast } from "./helpers/toast";
import { Logger } from "./helpers/logger";
import { ApiClient } from "./helpers/apiClient";
import { ApplicationState } from "./helpers/state";
import { Content } from "./pages/RenderDCSMenu";
import { Translator } from "./helpers/translator";
import { Storage } from "./helpers/storage";
import { Backend } from "./helpers/backend";
import { FaSave } from "react-icons/fa";
import ConfigurePathsPage from "./pages/ConfigurePathsPage";
import ConfigureBackendPage from "./pages/ConfigureBackendPage";
import RenderSyncLogPage from "./pages/RenderSyncLogPage";
import RenderPluginLogPage from "./pages/RenderPluginLogPage";

declare const appStore: any;

export default definePlugin((serverApi: ServerAPI) => {
  Storage.clearAllSessionStorage();
  ApplicationState.initialize(serverApi).then(async () => {
    Backend.initialize(serverApi);
    await Logger.initialize();
    await Translator.initialize();
  });

  serverApi.routerHook.addRoute("/dcs-configure-paths", () => <ConfigurePathsPage serverApi={serverApi} />, { exact: true });
  serverApi.routerHook.addRoute("/dcs-configure-backend", () => <ConfigureBackendPage serverApi={serverApi} />, { exact: true });
  serverApi.routerHook.addRoute("/dcs-sync-logs", () => <RenderSyncLogPage />, { exact: true });
  serverApi.routerHook.addRoute("/dcs-plugin-logs", () => <RenderPluginLogPage />, { exact: true });

  let removeGameExecutionListener: (() => void) | undefined;
  try {
    Logger.info("Registering game lifecycle listener");
    const reg = SteamClient.GameSessions.RegisterForAppLifetimeNotifications((e: LifetimeNotification) => {
      try {
        Logger.info("Game lifecycle event: " + JSON.stringify(e));
        const currentState = ApplicationState.getAppState().currentState;
        if (currentState.sync_on_game_exit !== "true") {
          Logger.info("sync_on_game_exit not enabled, skipping");
          return;
        }

        const appId = (e as any).unAppID ?? (e as any).nAppID ?? (e as any).appid;
        const isRunning = Boolean((e as any).bRunning ?? (e as any).running);
        const instanceId = Number((e as any).nInstanceID ?? (e as any).instanceId ?? 0);

        const gameInfo = appId != null ? appStore.GetAppOverviewByGameID(appId) : undefined;
        const gameName = gameInfo?.display_name ?? "Unknown";

        Logger.info((isRunning ? "Starting" : "Stopping") + " game '" + gameName + "' (" + String(appId ?? "unknown") + ")");
        ApplicationState.setAppState("playing", String(isRunning));

        syncGame(isRunning, instanceId);
      } catch (err) {
        Logger.error("Game lifetime callback failed: " + String(err));
      }
    });
    removeGameExecutionListener = reg?.unregister ?? reg?.Cancel ?? undefined;
    Logger.info("Game lifecycle listener registered: " + (removeGameExecutionListener ? "ok" : "no unregister fn"));
  } catch (regErr) {
    Logger.error("Failed to register game lifecycle listener: " + String(regErr));
  }

  return {
    title: <div className={staticClasses.Title}>Decky Cloud Save</div>,
    content: <Content />,
    icon: <FaSave />,
    onDismount() {
      removeGameExecutionListener?.();
      Storage.clearAllSessionStorage();
      serverApi.routerHook.removeRoute("/dcs-configure-paths");
      serverApi.routerHook.removeRoute("/dcs-configure-backend");
      serverApi.routerHook.removeRoute("/dcs-sync-logs");
      serverApi.routerHook.removeRoute("/dcs-plugin-logs");
    },
  };
});

function syncGame(isRunning: boolean, instanceId: number) {
  const currentState = ApplicationState.getAppState().currentState;
  let toast = currentState.toast_auto_sync === "true";
  if (isRunning) {
    // Only sync at start when bisync is enabled. No need to when its not.
    if (currentState.bisync_enabled === "true") {
      if (toast) {
        Toast.toast(Translator.translate("synchronizing.savedata"), 2000);
      }
      ApiClient.syncOnLaunch(toast, instanceId); // nInstanceID is Linux Process PID
    }
  } else {
    ApiClient.syncOnEnd(toast);
  }
}
