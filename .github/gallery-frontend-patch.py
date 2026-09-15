from pathlib import Path
p = Path('apps/web/app/forma-workspace.tsx')
s = p.read_text()
def rep(a, b):
    global s
    assert s.count(a) == 1, (a[:100], s.count(a))
    s = s.replace(a, b)
rep('import { useFormaAuth } from "../lib/forma-auth";', 'import { useFormaAuth } from "../lib/forma-auth";\nimport { GalleryImageRequests, GalleryPageCache, galleryPageKey } from "../lib/gallery-loading";')
rep('const NEW_PROJECT_TITLE = "New project";', 'const NEW_PROJECT_TITLE = "New project";\nconst EMPTY_GALLERY_IMAGES: Record<string, ProjectImageCandidate | null> = {};\nconst EMPTY_PROJECT_HISTORY: any[] = [];')
rep('  const chatStorageScope = authRequired ? `identity:${authIdentityKey}` : "local";', '  const chatStorageScope = authRequired ? `identity:${authIdentityKey}` : "local";\n  const galleryIdentityKey = JSON.stringify([API_URL, authRequired, authIdentityKey, Boolean(isSignedIn)]);')
rep('  const [projectHistoryLoaded, setProjectHistoryLoaded] = useState(false);', '''  const [projectHistoryLoaded, setProjectHistoryLoaded] = useState(false);
  const [projectHistoryKey, setProjectHistoryKey] = useState<string | null>(null);
  const [projectHistoryError, setProjectHistoryError] = useState<Error | null>(null);
  const projectPageCacheRef = useRef(new GalleryPageCache<{ items: any[]; total: number }>());
  const projectHistoryAbortRef = useRef<AbortController | null>(null);
  const galleryImageRequestsRef = useRef(new GalleryImageRequests<ProjectImageCandidate | null>());''')
rep('  const [projectGalleryImages, setProjectGalleryImages] = useState<Record<string, ProjectImageCandidate | null>>({});', '''  const [galleryImageState, setGalleryImageState] = useState<{
    scope: string; images: Record<string, ProjectImageCandidate | null>;
  }>({ scope: "", images: {} });''')
rep('  const projectGalleryItems = useMemo(', '''  const imageScopeKey = `${galleryIdentityKey}:${formaDevMode}`;
  const projectGalleryImages = galleryImageState.scope === imageScopeKey
    ? galleryImageState.images : EMPTY_GALLERY_IMAGES;
  const currentGalleryPageKey = galleryPageKey(
    galleryIdentityKey, PROJECT_GALLERY_PAGE_SIZE, projectHistoryPage, projectSearchQuery,
  );
  const cachedGalleryPage = projectPageCacheRef.current.get(currentGalleryPageKey);
  const hasCurrentGalleryPage = projectHistoryKey === currentGalleryPageKey;
  const visibleProjectHistory = hasCurrentGalleryPage
    ? projectHistory : cachedGalleryPage?.items || EMPTY_PROJECT_HISTORY;
  const visibleProjectTotal = hasCurrentGalleryPage
    ? projectHistoryTotal : cachedGalleryPage?.total || 0;
  const projectGalleryItems = useMemo(''')
rep('''      projectHistory,
      projectGalleryImages,''', '''      visibleProjectHistory,
      projectGalleryImages,''')
rep('    [authRequired, formaDevMode, isSignedIn, projectHistory, projectGalleryImages]', '    [authRequired, formaDevMode, isSignedIn, visibleProjectHistory, projectGalleryImages]')
rep('  const projectsPageLoading = !projectHistoryLoaded;', '  const projectsPageLoading = !(hasCurrentGalleryPage && projectHistoryLoaded) && !cachedGalleryPage;')
rep('''  const handleProjectHistoryPageChange = useCallback((page: number) => {
    setProjectHistoryLoaded(false);''', '''  const handleProjectHistoryPageChange = useCallback((page: number) => {''')
rep('''      if (nextQuery === projectSearchQuery) return;
      setProjectHistoryLoaded(false);''', '''      if (nextQuery === projectSearchQuery) return;''')
rep('''    setProjectHistory((projects) => (
      normalizedRecord.visibility''', '''    projectPageCacheRef.current.clear();
    setProjectHistory((projects) => (
      normalizedRecord.visibility''')
rep('''    setProjectHistory(apply);
    setMyProjectHistory(apply);''', '''    projectPageCacheRef.current.clear();
    setProjectHistory(apply);
    setMyProjectHistory(apply);''')
rep('''      setProjectHistory((projects) => projects.filter((project: any) => project?.project_id !== projectId));''', '''      projectPageCacheRef.current.clear();
      setProjectHistory((projects) => projects.filter((project: any) => project?.project_id !== projectId));''')
rep('''      setProjectGalleryImages((images) => {
        const next = { ...images };
        delete next[projectId];
        return next;
      });''', '''      setGalleryImageState((current) => {
        const images = { ...current.images };
        delete images[projectId];
        return { ...current, images };
      });''')
rep('''  useEffect(() => {
    if (homeView !== "projects") return;
    void fetchProjectHistory(projectHistoryPage, projectSearchQuery);''', '''  useLayoutEffect(() => {
    projectPageCacheRef.current.clear();
    projectHistoryRequestIdRef.current += 1;
    projectHistoryAbortRef.current?.abort();
    return () => {
      projectHistoryRequestIdRef.current += 1;
      projectHistoryAbortRef.current?.abort();
    };
  }, [galleryIdentityKey]);

  useEffect(() => {
    const requests = galleryImageRequestsRef.current;
    return () => requests.clear();
  }, []);

  useEffect(() => {
    if (homeView !== "projects") return;
    void fetchProjectHistory(projectHistoryPage, projectSearchQuery);''')
rep('  }, [homeView, projectHistoryPage, projectSearchQuery]);', '  }, [homeView, projectHistoryPage, projectSearchQuery, galleryIdentityKey, authLoaded]);')
start = s.index('  const fetchProjectHistory = async (')
end = s.index('  const fetchMyProjectHistory = async (', start)
s = s[:start] + '''  const fetchProjectHistory = async (
    page: number = projectHistoryPage,
    search: string = projectSearchQuery,
  ) => {
    const requestId = ++projectHistoryRequestIdRef.current;
    projectHistoryAbortRef.current?.abort();
    const controller = new AbortController();
    projectHistoryAbortRef.current = controller;
    const isCurrent = () => !controller.signal.aborted && projectHistoryRequestIdRef.current === requestId;
    const key = galleryPageKey(galleryIdentityKey, PROJECT_GALLERY_PAGE_SIZE, page, search);
    const cached = projectPageCacheRef.current.get(key);
    setProjectHistoryError(null);
    if (cached) {
      setProjectHistory(cached.items);
      setProjectHistoryTotal(cached.total);
      setProjectHistoryKey(key);
      setProjectHistoryLoaded(true);
    } else if (projectHistoryKey !== key) {
      setProjectHistoryLoaded(false);
    }
    // A same-page refresh keeps the current cards mounted. A cached page can
    // also render immediately, but every visit still revalidates permissions.
    try {
      const params = new URLSearchParams({
        limit: String(PROJECT_GALLERY_PAGE_SIZE),
        offset: String(Math.max(0, page) * PROJECT_GALLERY_PAGE_SIZE),
      });
      const normalizedSearch = search.trim();
      if (normalizedSearch) params.set("q", normalizedSearch);
      const headers = await optionalAuthHeaders();
      if (!isCurrent()) return;
      const res = await fetch(`${API_URL}/projects?${params.toString()}`, {
        signal: controller.signal,
        headers,
      });
      if (!isCurrent()) return;
      if (!res.ok) {
        if (isAuthOrSecurityHttpStatus(res.status)) {
          projectPageCacheRef.current.clear();
          setProjectHistory([]);
          setProjectHistoryTotal(0);
        }
        throw new Error(await readApiErrorMessage(res));
      }
      const result = normalizeProjectListPage(await res.json());
      if (!isCurrent()) return;
      projectPageCacheRef.current.set(key, result);
      setProjectHistory(result.items);
      setProjectHistoryTotal(result.total);
      setProjectHistoryKey(key);
      if (!authRequired) {
        setLocalChatItems((current) => {
          const repairedItems = buildChatListItems(result.items, current);
          writeStoredChatIndex(repairedItems, chatStorageScope);
          return repairedItems;
        });
      }
    } catch (error) {
      if (!isCurrent()) return;
      if (!cached && projectHistoryKey !== key) {
        setProjectHistory([]);
        setProjectHistoryTotal(0);
      }
      setProjectHistoryKey(key);
      setProjectHistoryError(error instanceof Error ? error : new Error("Projects could not be loaded."));
      console.error("Error fetching project history", error);
    } finally {
      if (isCurrent()) {
        setProjectHistoryLoaded(true);
        projectHistoryAbortRef.current = null;
      }
    }
  };

''' + s[end:]
start = s.index('  useEffect(() => {\n    if (currentRouteProjectId || projectIR) return;\n    const visibleProjectIds')
end = s.index('  const attachImageFile = ', start)
s = s[:start] + '''  useEffect(() => {
    const galleryActive = (homeView === "projects" || homeView === "my-projects")
      && !currentRouteProjectId && !projectIR;
    const visibleProjectIds = new Set(galleryActive ? visibleProjectGalleryIds : []);
    const imageProjects = homeView === "my-projects" ? myProjectHistory : visibleProjectHistory;
    const missingIds = imageProjects.filter((project: any) => {
      const projectId = project?.project_id ? String(project.project_id) : "";
      if (!visibleProjectIds.has(projectId) || projectGalleryImages[projectId] !== undefined) return false;
      return !resolveProjectImageCandidates({
        product_visual_sequence: project.product_visual_sequence,
        product_image_url: project.product_image_url,
        product_image_data: project.product_image_data,
        product_image_content_type: project.product_image_content_type,
        product_image_model: project.product_image_model,
        image_output_model: project.image_output_model,
      }, formaDevMode)[0];
    }).map((project: any) => String(project.project_id));
    const storeImage = (projectId: string, image: ProjectImageCandidate | null) => {
      setGalleryImageState((current) => ({
        scope: imageScopeKey,
        images: { ...(current.scope === imageScopeKey ? current.images : {}), [projectId]: image },
      }));
    };
    galleryImageRequestsRef.current.sync(
      imageScopeKey,
      missingIds,
      async (projectId, signal) => {
        const headers = await optionalAuthHeaders();
        signal.throwIfAborted();
        const res = await fetch(`${API_URL}/projects/${encodeURIComponent(projectId)}/image-summary`, {
          signal, headers,
        });
        if (!res.ok) return null;
        return resolveProjectImageCandidates(await res.json(), formaDevMode)[0] || null;
      },
      storeImage,
      (projectId, error) => {
        console.error("Error fetching project image", error);
        storeImage(projectId, null);
      },
    );
    // No per-render cleanup: settling one image must not abort its siblings.
    // sync cancels obsolete IDs/scope; the separate cleanup handles unmount.
  }, [formaDevMode, homeView, imageScopeKey, currentRouteProjectId, myProjectHistory, optionalAuthHeaders, visibleProjectHistory, projectGalleryImages, projectIR, visibleProjectGalleryIds]);

''' + s[end:]
rep('                totalItems={projectHistoryTotal}', '                totalItems={visibleProjectTotal}\n                error={hasCurrentGalleryPage && !visibleProjectHistory.length ? projectHistoryError : null}')
p.write_text(s)
