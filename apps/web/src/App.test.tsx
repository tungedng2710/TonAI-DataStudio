import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

describe("App", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        if (url.endsWith("/auth/me")) {
          return Promise.resolve({
            ok: false,
            status: 401,
            statusText: "Unauthorized",
            json: () => Promise.resolve({ detail: "Sign in", status: 401 }),
          });
        }
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ items: [] }) });
      }),
    );
  });

  it("prompts an anonymous user to create an account", async () => {
    render(<MemoryRouter><App /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("heading", { name: "Create your account" })).toBeInTheDocument();
  });

  it("renders the empty dataset hub state", async () => {
    render(<MemoryRouter><App /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "TonAI Data Studio home" })).toBeInTheDocument();
    expect(await screen.findByText("Datasets, clearly versioned.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Repositories" })).toBeInTheDocument();
    expect(await screen.findByText("Create your first dataset")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Search datasets")).not.toBeInTheDocument();
    expect(screen.getAllByRole("combobox", { name: "Search users and datasets" })).not.toHaveLength(0);
    expect(screen.getByRole("link", { name: "API guide" })).toHaveAttribute("href", "/docs/api");
  });

  it("searches for users and datasets and opens a public profile", async () => {
    const publicUser = {
      username: "researcher",
      display_name: "Vision Researcher",
      avatar_updated_at: null,
      created_at: "2026-07-22T08:00:00Z",
    };
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.endsWith("/auth/me")) {
        return Promise.resolve({
          ok: false,
          status: 401,
          statusText: "Unauthorized",
          json: () => Promise.resolve({ detail: "Sign in", status: 401 }),
        });
      }
      if (url.includes("/auth/users?q=vision&limit=8")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ items: [publicUser] }),
        });
      }
      if (url.includes("/datasets?search=vision&limit=8")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({
            items: [{
              id: "dataset-id",
              namespace: "researcher",
              slug: "research-images",
              visibility: "public",
              description: "Computer vision training images",
              data_stage: "training_ready",
              tags: ["vision"],
              default_branch: "main",
              created_at: "2026-07-22T08:00:00Z",
              updated_at: "2026-07-22T08:00:00Z",
              owner: "researcher",
              can_edit: false,
              latest_revision: null,
            }],
          }),
        });
      }
      if (url.endsWith("/auth/users/researcher")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(publicUser) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ items: [] }) });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<MemoryRouter><App /></MemoryRouter>);
    fireEvent.change(
      (await screen.findAllByRole("combobox", { name: "Search users and datasets" }))[0]!,
      { target: { value: "vision" } },
    );
    expect(await screen.findByRole("link", { name: /researcher\/research-images/ })).toHaveAttribute(
      "href",
      "/datasets/researcher/research-images",
    );
    fireEvent.click(await screen.findByRole("link", { name: /Vision Researcher/ }));

    expect(await screen.findByRole("heading", { name: "Vision Researcher" })).toBeInTheDocument();
    expect(screen.getByText("researcher")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Repositories/ })).toHaveAttribute(
      "href",
      "/users/researcher/repositories",
    );
  });

  it("renders the API usage guide", async () => {
    render(<MemoryRouter initialEntries={["/docs/api"]}><App /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Start using the API in minutes" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "3. Upload and publish" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "5. Download a repository" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Copy code" })).toHaveLength(10);
    const examples = Array.from(document.querySelectorAll("pre code")).map(
      (element) => element.textContent ?? "",
    );
    const uploadFiles = examples.find((example) => example.includes("files=@README.md"));
    const openUpload = examples.find((example) => example.includes("$DATASET/uploads"));
    expect(uploadFiles?.split("\n")).toContain("  --form 'files=@README.md' \\");
    expect(openUpload).toContain("--data '{\"data_stage\":\"raw\"}'");
    expect(screen.getByText(/generated revision ID as the message/)).toBeInTheDocument();
    expect(examples.every((example) => example.split("\n").every((line) => line.length < 88))).toBe(true);
  });

  it("lets a signed-in user manage account settings while keeping username read-only", async () => {
    const user = {
      id: "owner-id",
      username: "owner",
      display_name: "Owner",
      email: "owner@example.com",
      is_admin: false,
      avatar_updated_at: null,
      created_at: "2026-07-22T08:00:00Z",
    };
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.endsWith("/auth/me") && init?.method === "PATCH") {
        const body = JSON.parse(typeof init.body === "string" ? init.body : "{}") as {
          display_name: string;
          email: string;
        };
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ ...user, ...body }),
        });
      }
      if (url.endsWith("/auth/password") && init?.method === "PUT") {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(user) });
      }
      if (url.endsWith("/auth/avatar") && init?.method === "PUT") {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({
            ...user,
            avatar_updated_at: "2026-07-28T10:00:00Z",
          }),
        });
      }
      if (url.endsWith("/auth/tokens") && init?.method === "POST") {
        return Promise.resolve({
          ok: true,
          status: 201,
          json: () => Promise.resolve({
            id: "token-id",
            name: "My CLI",
            token_prefix: "ds_pat_example",
            token: "ds_pat_example_secret",
            scopes: ["read", "write"],
            expires_at: null,
            last_used_at: null,
            created_at: "2026-07-22T08:00:00Z",
          }),
        });
      }
      if (url.endsWith("/auth/tokens")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
      }
      if (url.endsWith("/auth/me")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(user) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ items: [] }) });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<MemoryRouter initialEntries={["/settings"]}><App /></MemoryRouter>);

    expect(await screen.findByRole("heading", { name: "Account settings" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /Username/ })).toHaveAttribute("readonly");
    fireEvent.click(screen.getByRole("button", { name: "Open user menu" }));
    expect(screen.getByRole("menuitem", { name: "Your profile" })).toHaveAttribute(
      "href",
      "/users/owner",
    );
    expect(screen.getByRole("menuitem", { name: "User settings" })).toHaveAttribute(
      "href",
      "/settings",
    );
    expect(screen.getByRole("menuitem", { name: "Log out" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open user menu" }));

    const avatar = new File([new Uint8Array([137, 80, 78, 71])], "avatar.png", {
      type: "image/png",
    });
    fireEvent.change(screen.getByLabelText("Avatar image"), { target: { files: [avatar] } });
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/auth/avatar",
        expect.objectContaining({ method: "PUT" }),
      );
    });

    fireEvent.change(screen.getByRole("textbox", { name: "Name" }), {
      target: { value: "Updated Owner" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Email" }), {
      target: { value: "updated@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/auth/me",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({
            display_name: "Updated Owner",
            email: "updated@example.com",
          }),
        }),
      );
    });

    const passwordFields = screen.getAllByLabelText("Current password");
    fireEvent.change(passwordFields[0]!, { target: { value: "secure-password" } });
    fireEvent.change(screen.getByLabelText("New password"), {
      target: { value: "replacement-password" },
    });
    fireEvent.change(screen.getByLabelText("Confirm new password"), {
      target: { value: "replacement-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/auth/password",
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({
            current_password: "secure-password",
            new_password: "replacement-password",
          }),
        }),
      );
    });

    fireEvent.change(screen.getByRole("textbox", { name: "Token name" }), {
      target: { value: "My CLI" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate token" }));
    expect(await screen.findByDisplayValue("ds_pat_example_secret")).toHaveAttribute("readonly");
  });

  it("shows repositories created by the selected user", async () => {
    const user = {
      id: "owner-id",
      username: "owner",
      display_name: "Owner",
      email: null,
      is_admin: false,
      avatar_updated_at: null,
      created_at: "2026-07-22T08:00:00Z",
    };
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.endsWith("/auth/me")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(user) });
      }
      if (url.endsWith("/auth/users/owner")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(user) });
      }
      if (url.endsWith("/datasets?owner=owner")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({
            items: [
              {
                id: "dataset-id",
                namespace: "owner",
                slug: "my-data",
                visibility: "private",
                description: "Owned repository",
                data_stage: "training_ready",
                tags: ["license-plates", "vietnam"],
                default_branch: "main",
                created_at: "2026-07-22T08:00:00Z",
                updated_at: "2026-07-22T08:00:00Z",
                owner: "owner",
                can_edit: true,
                latest_revision: null,
              },
              {
                id: "public-dataset-id",
                namespace: "someone-else",
                slug: "public-data",
                visibility: "public",
                description: "Another user's public repository",
                default_branch: "main",
                created_at: "2026-07-22T08:00:00Z",
                updated_at: "2026-07-22T08:00:00Z",
                owner: "someone-else",
                can_edit: false,
                latest_revision: null,
              },
            ],
          }),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ items: [] }) });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/users/owner/repositories"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Owner's repositories" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "my-data" })).toBeInTheDocument();
    expect(screen.getByText("Training Ready")).toBeInTheDocument();
    expect(screen.getByText("license-plates")).toBeInTheDocument();
    expect(screen.getByText("vietnam")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "public-data" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/datasets?owner=owner",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("lets a signed-in user follow and unfollow another user", async () => {
    const currentUser = {
      id: "viewer-id",
      username: "viewer",
      display_name: "Viewer",
      email: null,
      is_admin: false,
      avatar_updated_at: null,
      created_at: "2026-07-22T08:00:00Z",
    };
    let isFollowing = false;
    const profile = () => ({
      username: "researcher",
      display_name: "Vision Researcher",
      avatar_updated_at: null,
      created_at: "2026-07-22T08:00:00Z",
      followers_count: isFollowing ? 4 : 3,
      following_count: 8,
      is_following: isFollowing,
    });
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.endsWith("/auth/me")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(currentUser) });
      }
      if (url.endsWith("/auth/users/researcher/follow")) {
        isFollowing = init?.method === "PUT";
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(profile()) });
      }
      if (url.endsWith("/auth/users/researcher")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(profile()) });
      }
      if (url.endsWith("/datasets?owner=researcher")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ items: [] }) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ items: [] }) });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/users/researcher"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Follow" }));
    expect(await screen.findByRole("button", { name: "Following" })).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/auth/users/researcher/follow",
      expect.objectContaining({ method: "PUT", credentials: "include" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Following" }));
    expect(await screen.findByRole("button", { name: "Follow" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/auth/users/researcher/follow",
      expect.objectContaining({ method: "DELETE", credentials: "include" }),
    );
  });

  it("shows a user's followers and allows following from the list", async () => {
    const currentUser = {
      id: "viewer-id",
      username: "viewer",
      display_name: "Viewer",
      email: null,
      is_admin: false,
      avatar_updated_at: null,
      created_at: "2026-07-22T08:00:00Z",
    };
    const profile = {
      username: "researcher",
      display_name: "Vision Researcher",
      avatar_updated_at: null,
      created_at: "2026-07-22T08:00:00Z",
      followers_count: 1,
      following_count: 2,
      is_following: false,
    };
    let followsCollaborator = false;
    const collaborator = () => ({
      username: "collaborator",
      display_name: "Data Collaborator",
      avatar_updated_at: null,
      created_at: "2026-07-23T08:00:00Z",
      followers_count: followsCollaborator ? 6 : 5,
      following_count: 3,
      is_following: followsCollaborator,
    });
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.endsWith("/auth/me")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(currentUser) });
      }
      if (url.endsWith("/auth/users/researcher")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(profile) });
      }
      if (url.includes("/auth/users/researcher/followers?offset=0&limit=50")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ items: [collaborator()], total: 1, offset: 0, limit: 50 }),
        });
      }
      if (url.endsWith("/auth/users/collaborator/follow")) {
        followsCollaborator = init?.method === "PUT";
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(collaborator()) });
      }
      if (url.endsWith("/datasets?owner=researcher")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ items: [] }) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ items: [] }) });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/users/researcher/followers"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Followers" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Data Collaborator" })).toHaveAttribute(
      "href",
      "/users/collaborator",
    );
    expect(screen.getByRole("link", { name: /1 followers/ })).toHaveAttribute(
      "href",
      "/users/researcher/followers",
    );
    expect(screen.getByRole("link", { name: /2 following/ })).toHaveAttribute(
      "href",
      "/users/researcher/following",
    );

    fireEvent.click(screen.getByRole("button", { name: "Follow collaborator" }));
    expect(await screen.findByRole("button", { name: "Unfollow collaborator" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/auth/users/collaborator/follow",
      expect.objectContaining({ method: "PUT", credentials: "include" }),
    );
  });

  it("highlights the active workspace tab", async () => {
    const createdAt = "2026-07-22T08:00:00Z";
    const longDescription = "A detailed dataset description ".repeat(20).trim();
    const summary = {
      revision_id: "abc123",
      branch: "main",
      commit_message: "Initial import",
      status: "ready",
      manifest_sha256: "0".repeat(64),
      error_code: null,
      error_message: null,
      created_at: createdAt,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        let body: unknown;
        if (url.endsWith("/auth/me")) {
          return Promise.resolve({
            ok: false,
            status: 401,
            statusText: "Unauthorized",
            json: () => Promise.resolve({ detail: "Sign in", status: 401 }),
          });
        } else if (url.includes("/revisions/abc123")) {
          body = {
            ...summary,
            card_markdown: "",
            card_html: "",
            card_metadata: {},
            files: [],
            configs: [],
          };
        } else if (url.endsWith("/revisions")) {
          body = [summary];
        } else if (url.includes("/tree/abc123/page")) {
          body = { items: [], total: 0, offset: 0, limit: 100 };
        } else {
          body = {
            id: "dataset-id",
            namespace: "research",
            slug: "demo",
            visibility: "private",
            description: longDescription,
            data_stage: "raw_validated",
            tags: ["ocr", "images"],
            default_branch: "main",
            created_at: createdAt,
            updated_at: createdAt,
            owner: "research",
            can_edit: false,
            latest_revision: summary,
          };
        }
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
      }),
    );

    render(
      <MemoryRouter initialEntries={["/datasets/research/demo/files?revision=abc123"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Repository files")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Files" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Dataset card" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "research" })).toHaveAttribute(
      "href",
      "/users/research",
    );
    expect(screen.getByText("Raw Validated")).toBeInTheDocument();
    expect(screen.getByText("ocr")).toBeInTheDocument();
    expect(screen.getByText("images")).toBeInTheDocument();
    expect(screen.getByTitle(longDescription)).toHaveClass("min-w-0", "truncate");
    expect(screen.getByRole("link", { name: "Download dataset" })).toHaveClass("shrink-0");
    expect(screen.getByRole("link", { name: "Download dataset" })).toHaveAttribute(
      "href",
      "/api/v1/datasets/research/demo/archive/abc123",
    );
    fireEvent.click(screen.getByRole("link", { name: "Dataset card" }));
    expect(await screen.findByText("This dataset has no card yet")).toBeInTheDocument();
    expect(screen.queryByText("Dataset metadata")).not.toBeInTheDocument();
    expect(screen.queryByText("Ready to browse")).not.toBeInTheDocument();
  });

  it("lets an owner rename and delete a dataset before its first revision", async () => {
    let currentSlug = "test-dataset";
    const datasetPayload = () => ({
      id: "dataset-id",
      namespace: "owner",
      slug: currentSlug,
      visibility: "private",
      description: "",
      default_branch: "main",
      created_at: "2026-07-22T08:00:00Z",
      updated_at: "2026-07-22T08:00:00Z",
      owner: "owner",
      can_edit: true,
      latest_revision: null,
    });
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.endsWith("/auth/me")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({
            id: "owner-id",
            username: "owner",
            display_name: "Owner",
            email: null,
            is_admin: false,
            created_at: "2026-07-22T08:00:00Z",
          }),
        });
      }
      if (init?.method === "DELETE") {
        return Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve({}) });
      }
      if (init?.method === "PATCH") {
        const body = typeof init.body === "string" ? init.body : "{}";
        currentSlug = (JSON.parse(body) as { slug: string }).slug;
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(datasetPayload()) });
      }
      if (url.endsWith("/revisions")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
      }
      if (url.endsWith("/datasets")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ items: [] }) });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(datasetPayload()),
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/datasets/owner/test-dataset/settings"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("No optional tags.")).toBeInTheDocument();
    fireEvent.change(await screen.findByRole("textbox", { name: /Dataset name/ }), {
      target: { value: "renamed-dataset" },
    });
    expect(screen.getByRole("combobox", { name: "Dataset data stage" })).toBeDisabled();
    expect(
      screen.getByText("Choose the initial stage when publishing the first upload."),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "New dataset tag" }), {
      target: { value: "License Plates" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add tag" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/datasets/owner/test-dataset",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({
            slug: "renamed-dataset",
            description: "",
            visibility: "private",
            tags: ["license-plates"],
          }),
        }),
      );
    });

    expect(await screen.findByRole("heading", { name: "renamed-dataset" })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Delete dataset" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Confirm dataset name" }), {
      target: { value: "renamed-dataset" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Permanently delete" }));

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/datasets/owner/renamed-dataset",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });

  it("creates a revision with a default commit message when data stage changes", async () => {
    const summary = {
      revision_id: "rev-one",
      branch: "main",
      commit_message: "Initial upload",
      data_stage: "raw",
      status: "ready",
      manifest_sha256: "a".repeat(64),
      error_code: null,
      error_message: null,
      created_at: "2026-08-04T08:00:00Z",
    };
    let dataset = {
      id: "dataset-id",
      namespace: "owner",
      slug: "stage-data",
      visibility: "private",
      description: "",
      data_stage: "raw",
      tags: [],
      default_branch: "main",
      created_at: "2026-08-04T08:00:00Z",
      updated_at: "2026-08-04T08:00:00Z",
      owner: "owner",
      can_edit: true,
      latest_revision: summary,
    };
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.endsWith("/auth/me")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({
            id: "owner-id",
            username: "owner",
            display_name: "Owner",
            email: null,
            is_admin: false,
            avatar_updated_at: null,
            created_at: "2026-08-04T08:00:00Z",
          }),
        });
      }
      if (url.endsWith("/revisions")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([summary]) });
      }
      if (url.includes("/revisions/rev-")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({
            ...dataset.latest_revision,
            card_markdown: "",
            card_html: "",
            card_metadata: {},
            files: [],
            configs: [],
          }),
        });
      }
      if (url.endsWith("/stage") && init?.method === "POST") {
        const nextSummary = {
          ...summary,
          revision_id: "rev-two",
          data_stage: "training_ready",
          commit_message: "Stage update",
        };
        dataset = { ...dataset, data_stage: "training_ready", latest_revision: nextSummary };
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(dataset) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(dataset) });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/datasets/owner/stage-data/settings"]}>
        <App />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("combobox", { name: "Dataset data stage" }));
    fireEvent.click(screen.getByRole("option", { name: /Training ready/ }));
    const message = screen.getByRole("textbox", { name: /Stage commit message/ });
    expect((message as HTMLTextAreaElement).value).toMatch(
      /^change from stage raw to stage training ready at \d{4}-\d{2}-\d{2}T/,
    );
    const defaultMessage = (message as HTMLTextAreaElement).value;
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/datasets/owner/stage-data/stage",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            data_stage: "training_ready",
            commit_message: defaultMessage,
          }),
        }),
      );
    });
  });
});
