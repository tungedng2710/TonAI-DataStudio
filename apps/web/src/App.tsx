import { Route, Routes } from "react-router-dom";

import { AuthProvider } from "./components/Auth";
import { ApiDocsPage } from "./pages/ApiDocsPage";
import { AccountSettingsPage } from "./pages/AccountSettingsPage";
import { DatasetsPage } from "./pages/DatasetsPage";
import { DatasetWorkspace } from "./pages/DatasetWorkspace";
import { UserRepositoriesPage } from "./pages/UserRepositoriesPage";

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<DatasetsPage />} />
        <Route path="/docs/api" element={<ApiDocsPage />} />
        <Route path="/settings" element={<AccountSettingsPage />} />
        <Route path="/users/:username" element={<UserRepositoriesPage />} />
        <Route path="/users/:username/repositories" element={<UserRepositoriesPage />} />
        <Route path="/users/:username/followers" element={<UserRepositoriesPage />} />
        <Route path="/users/:username/following" element={<UserRepositoriesPage />} />
        <Route path="/datasets/:namespace/:dataset/*" element={<DatasetWorkspace />} />
      </Routes>
    </AuthProvider>
  );
}
