"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useFormaAuth } from "./forma-auth";
import { webConfig } from "./config";
import { normalizeApiUrl, readFabricationSettings, type FabricationSettings } from "./fabrication-settings";

const API_URL = normalizeApiUrl(webConfig.apiBaseUrl);

export function useFabricationSettings() {
  const { hasIdentity, identityKey, isLoaded, getToken } = useFormaAuth();
  const [settings, setSettings] = useState<FabricationSettings | null>(null);
  const [printerId, setPrinterId] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const generation = useRef(0);
  const savingRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const current = ++generation.current;
    setSettings(null);
    setPrinterId("");
    setNotice(null);
    setError(null);
    setSaving(false);
    setLoading(true);
    if (!isLoaded || !hasIdentity) {
      setLoading(!isLoaded);
      return () => { generation.current++; controller.abort(); savingRequest.current?.abort(); savingRequest.current = null; };
    }
    void (async () => {
      try {
        const token = await getToken();
        if (controller.signal.aborted) return;
        const response = await fetch(`${API_URL}/user/settings/fabrication`, {
          headers: { Accept: "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          cache: "no-store", signal: controller.signal,
        });
        if (!response.ok) throw new Error("Printer settings could not be loaded. Please retry.");
        const next = readFabricationSettings(await response.json());
        if (current !== generation.current) return;
        setSettings(next);
        setPrinterId(next.printer_id);
      } catch (cause) {
        if (current === generation.current && !controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "Printer settings could not be loaded.");
        }
      } finally {
        if (current === generation.current) setLoading(false);
      }
    })();
    return () => { generation.current++; controller.abort(); savingRequest.current?.abort(); savingRequest.current = null; };
  }, [getToken, hasIdentity, identityKey, isLoaded, revision]);

  const selectPrinter = useCallback((value: string) => {
    setPrinterId(value);
    setNotice(null);
    setError(null);
  }, []);

  const save = useCallback(async () => {
    if (!settings || !hasIdentity || loading || saving || savingRequest.current
      || !settings.printers.some((printer) => printer.printer_id === printerId)) return;
    const current = generation.current;
    const controller = new AbortController();
    savingRequest.current = controller;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const token = await getToken();
      if (controller.signal.aborted) return;
      const response = await fetch(`${API_URL}/user/settings/fabrication`, {
        method: "PUT", cache: "no-store", signal: controller.signal,
        headers: { "Content-Type": "application/json", Accept: "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ printer_id: printerId }),
      });
      if (!response.ok) throw new Error("Printer settings were not saved. Please retry.");
      const next = readFabricationSettings(await response.json());
      if (current !== generation.current || controller.signal.aborted) return;
      setSettings(next);
      setPrinterId(next.printer_id);
      setNotice("Printer preference saved to your account.");
    } catch (cause) {
      if (current === generation.current && !controller.signal.aborted) {
        setError(cause instanceof Error ? cause.message : "Printer settings were not saved.");
      }
    } finally {
      if (savingRequest.current === controller) savingRequest.current = null;
      if (current === generation.current) setSaving(false);
    }
  }, [getToken, hasIdentity, loading, printerId, saving, settings]);

  return { settings, printerId, selectPrinter, loading, saving, error, notice, save,
    refresh: () => setRevision((value) => value + 1),
    dirty: Boolean(settings && (settings.source !== "user" || settings.printer_id !== printerId)) };
}

export type FabricationSettingsState = ReturnType<typeof useFabricationSettings>;
