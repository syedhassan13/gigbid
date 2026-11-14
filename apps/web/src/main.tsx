import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./styles.css";
import Layout from "./components/Layout";
import { getToken } from "./lib/api/client";
import Login from "./app/login";
import Onboarding from "./app/onboarding/page";
import Inbox from "./app/inbox/page";
import JobDetail from "./app/jobs/[id]/page";
import Studio from "./app/studio/[id]/page";
import Pipeline from "./app/pipeline/page";
import Messages from "./app/messages/page";
import Runs from "./app/runs/page";
import RunViewer from "./app/runs/[id]/page";
import Analytics from "./app/analytics/page";
import Settings from "./app/settings/page";

function Private({ children }: { children: React.ReactNode }) {
  return getToken() ? <>{children}</> : <Navigate to="/login" replace />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/onboarding" element={<Private><Onboarding /></Private>} />
        <Route element={<Private><Layout /></Private>}>
          <Route path="/" element={<Navigate to="/inbox" replace />} />
          <Route path="/inbox" element={<Inbox />} />
          <Route path="/jobs/:id" element={<JobDetail />} />
          <Route path="/studio/:id" element={<Studio />} />
          <Route path="/pipeline" element={<Pipeline />} />
          <Route path="/messages" element={<Messages />} />
          <Route path="/runs" element={<Runs />} />
          <Route path="/runs/:id" element={<RunViewer />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/inbox" replace />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
