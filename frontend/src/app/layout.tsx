import type { Metadata } from "next";
import "../components/Navigation";
import Navigation from "../components/Navigation";

export const metadata: Metadata = {
  title: "B2B Outreach MVP",
  description: "AI-Powered B2B Outreach Platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`bg-[#0A0A0A] text-gray-100 min-h-screen flex flex-col font-sans`}>
        <Navigation />
        <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8">
          {children}
        </main>
      </body>
    </html>
  );
}
