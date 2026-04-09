import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "../components/shared/Sidebar";
import { AlertBanner } from "../components/shared/AlertBanner";
import { WSProvider } from "../components/shared/WSProvider";

export const metadata: Metadata = {
  title: "ATLAS — Trading Command Center",
  description: "Autonomous Trading & Learning Agent System",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-gray-100 min-h-screen flex">
        <WSProvider>
          <Sidebar />
          <main className="flex-1 flex flex-col min-h-screen ml-64">
            <AlertBanner />
            <div className="flex-1 p-6">{children}</div>
          </main>
        </WSProvider>
      </body>
    </html>
  );
}
