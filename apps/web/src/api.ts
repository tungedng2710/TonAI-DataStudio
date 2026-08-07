import type {
  ApiToken,
  ApiTokenCreated,
  DataStage,
  Dataset,
  DatasetConfig,
  FilePage,
  Problem,
  PublicUser,
  PublicUserPage,
  Revision,
  RevisionSummary,
  User,
  ViewerResponse,
  Visibility,
} from "./types";
import { repositoryPathForUpload } from "./upload-paths";

const API_ROOT = import.meta.env.VITE_API_URL ?? "/api/v1";

type DatasetResponse = Omit<Dataset, "data_stage" | "tags"> &
  Partial<Pick<Dataset, "data_stage" | "tags">>;

function normalizeDataset(dataset: DatasetResponse): Dataset {
  return {
    ...dataset,
    data_stage: dataset.data_stage ?? null,
    tags: dataset.tags ?? [],
  };
}

export interface UploadProgress {
  phase: "preparing" | "uploading" | "publishing";
  message: string;
  uploadedFiles: number;
  totalFiles: number;
  uploadedBytes: number;
  totalBytes: number;
}

export class ApiError extends Error {
  readonly problem: Problem;

  constructor(problem: Problem) {
    super(problem.detail);
    this.name = "ApiError";
    this.problem = problem;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const fallback: Problem = {
      title: "Request failed",
      detail: `${response.status} ${response.statusText}`,
      status: response.status,
      code: "request_failed",
    };
    const problem = (await response.json().catch(() => fallback)) as Problem;
    throw new ApiError(problem);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  currentUser(): Promise<User> {
    return request("/auth/me");
  },

  register(body: {
    username: string;
    display_name: string;
    email: string;
    password: string;
  }): Promise<User> {
    return request("/auth/register", { method: "POST", body: JSON.stringify(body) });
  },

  login(body: { username: string; password: string }): Promise<User> {
    return request("/auth/login", { method: "POST", body: JSON.stringify(body) });
  },

  logout(): Promise<void> {
    return request("/auth/logout", { method: "POST" });
  },

  updateProfile(body: { display_name: string; email: string | null }): Promise<User> {
    return request("/auth/me", { method: "PATCH", body: JSON.stringify(body) });
  },

  changePassword(body: { current_password: string; new_password: string }): Promise<User> {
    return request("/auth/password", { method: "PUT", body: JSON.stringify(body) });
  },

  uploadAvatar(file: File): Promise<User> {
    const form = new FormData();
    form.append("avatar", file);
    return request("/auth/avatar", { method: "PUT", body: form });
  },

  avatarUrl(username: string, version: string): string {
    const params = new URLSearchParams({ v: version });
    return `${API_ROOT}/auth/users/${encodeURIComponent(username)}/avatar?${params}`;
  },

  user(username: string): Promise<PublicUser> {
    return request(`/auth/users/${encodeURIComponent(username)}`);
  },

  followUser(username: string): Promise<PublicUser> {
    return request(`/auth/users/${encodeURIComponent(username)}/follow`, { method: "PUT" });
  },

  unfollowUser(username: string): Promise<PublicUser> {
    return request(`/auth/users/${encodeURIComponent(username)}/follow`, { method: "DELETE" });
  },

  followers(username: string, offset = 0, limit = 50): Promise<PublicUserPage> {
    const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    return request(`/auth/users/${encodeURIComponent(username)}/followers?${params}`);
  },

  following(username: string, offset = 0, limit = 50): Promise<PublicUserPage> {
    const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    return request(`/auth/users/${encodeURIComponent(username)}/following?${params}`);
  },

  async searchUsers(query: string, limit = 8): Promise<PublicUser[]> {
    const params = new URLSearchParams({ q: query, limit: String(limit) });
    const response = await request<{ items: PublicUser[] }>(`/auth/users?${params}`);
    return response.items;
  },

  listTokens(): Promise<ApiToken[]> {
    return request("/auth/tokens");
  },

  createToken(body: { name: string; scopes: ("read" | "write")[] }): Promise<ApiTokenCreated> {
    return request("/auth/tokens", { method: "POST", body: JSON.stringify(body) });
  },

  revokeToken(tokenId: string): Promise<void> {
    return request(`/auth/tokens/${encodeURIComponent(tokenId)}`, { method: "DELETE" });
  },

  deleteAccount(password: string): Promise<void> {
    return request("/auth/me", {
      method: "DELETE",
      body: JSON.stringify({ password }),
    });
  },

  async listDatasets(owner?: string): Promise<Dataset[]> {
    const suffix = owner
      ? `?${new URLSearchParams({ owner }).toString()}`
      : "";
    const response = await request<{ items: DatasetResponse[] }>(`/datasets${suffix}`);
    return response.items.map(normalizeDataset);
  },

  async searchDatasets(query: string, limit = 8): Promise<Dataset[]> {
    const params = new URLSearchParams({ search: query, limit: String(limit) });
    const response = await request<{ items: DatasetResponse[] }>(`/datasets?${params}`);
    return response.items.map(normalizeDataset);
  },

  async createDataset(body: {
    namespace: string;
    slug: string;
    visibility: Visibility;
    description: string;
    data_stage?: DataStage | null;
    tags?: string[];
  }): Promise<Dataset> {
    const dataset = await request<DatasetResponse>("/datasets", {
      method: "POST",
      body: JSON.stringify(body),
    });
    return normalizeDataset(dataset);
  },

  async updateDataset(
    namespace: string,
    dataset: string,
    body: {
      slug?: string;
      visibility?: Visibility;
      description?: string;
      data_stage?: DataStage | null;
      tags?: string[];
    },
  ): Promise<Dataset> {
    const updated = await request<DatasetResponse>(
      `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}`,
      {
        method: "PATCH",
        body: JSON.stringify(body),
      },
    );
    return normalizeDataset(updated);
  },

  async changeDataStage(
    namespace: string,
    dataset: string,
    body: { data_stage: DataStage | null; commit_message: string },
  ): Promise<Dataset> {
    const updated = await request<DatasetResponse>(
      `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}/stage`,
      { method: "POST", body: JSON.stringify(body) },
    );
    return normalizeDataset(updated);
  },

  deleteDataset(namespace: string, dataset: string): Promise<void> {
    return request(`/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}`, {
      method: "DELETE",
    });
  },

  async dataset(namespace: string, dataset: string): Promise<Dataset> {
    const response = await request<DatasetResponse>(
      `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}`,
    );
    return normalizeDataset(response);
  },

  revision(namespace: string, dataset: string, revision = "main"): Promise<Revision> {
    const params = new URLSearchParams({ include_files: "false" });
    return request(
      `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}/revisions/${encodeURIComponent(revision)}?${params}`,
    );
  },

  filePage(
    namespace: string,
    dataset: string,
    revision: string,
    options: { offset?: number; limit?: number; search?: string },
  ): Promise<FilePage> {
    const params = new URLSearchParams({
      offset: String(options.offset ?? 0),
      limit: String(options.limit ?? 100),
    });
    if (options.search) params.set("search", options.search);
    return request(
      `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}/tree/${encodeURIComponent(revision)}/page?${params}`,
    );
  },

  revisions(namespace: string, dataset: string): Promise<RevisionSummary[]> {
    return request(
      `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}/revisions`,
    );
  },

  configs(namespace: string, dataset: string, revision: string): Promise<DatasetConfig[]> {
    const params = new URLSearchParams({ revision });
    return request(
      `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}/configs?${params}`,
    );
  },

  viewer(
    namespace: string,
    dataset: string,
    config: string,
    split: string,
    options: { revision: string; offset?: number; limit?: number; filter?: string },
  ): Promise<ViewerResponse> {
    const params = new URLSearchParams({
      revision: options.revision,
      offset: String(options.offset ?? 0),
      limit: String(options.limit ?? 100),
    });
    if (options.filter) params.set("filter", options.filter);
    return request(
      `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}/viewer/${encodeURIComponent(config)}/${encodeURIComponent(split)}?${params}`,
    );
  },

  viewerMediaUrl(
    namespace: string,
    dataset: string,
    config: string,
    split: string,
    row: number,
    column: string,
    revision: string,
    thumbnail = true,
  ): string {
    const params = new URLSearchParams({
      revision,
      thumbnail: String(thumbnail),
    });
    const path = [
      namespace,
      dataset,
      "viewer-media",
      config,
      split,
      String(row),
      column,
    ].map(encodeURIComponent).join("/");
    return `${API_ROOT}/datasets/${path}?${params.toString()}`;
  },

  statistics(
    namespace: string,
    dataset: string,
    config: string,
    split: string,
    revision: string,
  ): Promise<Record<string, unknown>> {
    const params = new URLSearchParams({ revision });
    return request(
      `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}/statistics/${encodeURIComponent(config)}/${encodeURIComponent(split)}?${params}`,
    );
  },

  async uploadFiles(
    namespace: string,
    dataset: string,
    files: File[],
    commitMessage: string,
    dataStage: DataStage | null | undefined,
    onProgress: (progress: UploadProgress) => void,
    signal?: AbortSignal,
  ): Promise<Revision> {
    const totalBytes = files.reduce((total, file) => total + file.size, 0);
    const report = (
      phase: UploadProgress["phase"],
      message: string,
      uploadedFiles = 0,
      uploadedBytes = 0,
    ) => onProgress({ phase, message, uploadedFiles, totalFiles: files.length, uploadedBytes, totalBytes });
    report("preparing", "Creating a secure upload session…");
    const upload = await request<{ id: string }>(
      `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}/uploads`,
      {
        method: "POST",
        body: JSON.stringify({
          commit_message: commitMessage,
          ...(dataStage !== undefined ? { data_stage: dataStage } : {}),
        }),
        signal,
      },
    );

    let uploadedFiles = 0;
    let uploadedBytes = 0;
    let index = 0;
    let batchNumber = 0;
    const maxBatchFiles = 200;
    const maxBatchBytes = 128 * 1024 * 1024;
    while (index < files.length) {
      const batch: File[] = [];
      let batchBytes = 0;
      while (index < files.length && batch.length < maxBatchFiles) {
        const candidate = files[index];
        if (!candidate) break;
        if (batch.length && batchBytes + candidate.size > maxBatchBytes) break;
        batch.push(candidate);
        batchBytes += candidate.size;
        index += 1;
        if (candidate.size >= maxBatchBytes) break;
      }
      const form = new FormData();
      batchNumber += 1;
      for (const file of batch) {
        form.append("files", file, file.name);
        form.append("paths", repositoryPathForUpload(file));
      }
      report(
        "uploading",
        `Uploading batch ${batchNumber.toLocaleString()}…`,
        uploadedFiles,
        uploadedBytes,
      );
      await request(`/uploads/${upload.id}/files`, { method: "POST", body: form, signal });
      uploadedFiles += batch.length;
      uploadedBytes += batchBytes;
      report(
        "uploading",
        `${uploadedFiles.toLocaleString()} of ${files.length.toLocaleString()} files uploaded`,
        uploadedFiles,
        uploadedBytes,
      );
    }

    report("publishing", "Validating, indexing, and publishing the immutable revision…", uploadedFiles, uploadedBytes);
    return request(`/uploads/${upload.id}/complete?include_files=false`, {
      method: "POST",
      body: JSON.stringify({ expected_file_count: files.length }),
      signal,
    });
  },

  blobUrl(
    namespace: string,
    dataset: string,
    revision: string,
    path: string,
    inline = false,
  ): string {
    const encodedPath = path.split("/").map(encodeURIComponent).join("/");
    const suffix = inline ? "?inline=true" : "";
    return `${API_ROOT}/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}/blob/${encodeURIComponent(revision)}/${encodedPath}${suffix}`;
  },

  archiveUrl(namespace: string, dataset: string, revision: string): string {
    return `${API_ROOT}/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}/archive/${encodeURIComponent(revision)}`;
  },
};
