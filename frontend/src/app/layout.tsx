import "./globals.css";
import type { Metadata } from "next";
import Sidebar from "@/components/Sidebar";
import Header from "@/components/Header";
import { LocationProvider } from "@/components/LocationProvider";

export const metadata: Metadata = {
  title: "AeroBlend AI — Hybrid AI–NWP Multi-Model Forecast Blending System",
  description: "Operational meteorological platform dynamically blending numerical weather prediction (ECMWF, GFS, ICON) and AI models with deep learning gating networks.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200"
          rel="stylesheet"
        />
        <link
          rel="stylesheet"
          href="https://cesium.com/downloads/cesiumjs/releases/1.120/Build/Cesium/Widgets/widgets.css"
        />
      </head>
      <body className="bg-background font-body-md text-on-surface antialiased min-h-screen relative overflow-x-hidden selection:bg-primary selection:text-on-primary">
        {/* Soft abstract blurred atmospheric ribbons from Stitch Design */}
        <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden">
          <div className="absolute -top-[25%] -left-[15%] w-[65vw] h-[65vw] rounded-full bg-secondary-fixed/40 blur-[130px]" />
          <div className="absolute top-[20%] -right-[15%] w-[55vw] h-[55vw] rounded-full bg-primary-fixed/45 blur-[140px]" />
          <div className="absolute -bottom-[20%] left-[25%] w-[50vw] h-[50vw] rounded-full bg-tertiary-fixed/30 blur-[150px]" />
        </div>

        {/* Fixed Left Navigation */}
        <LocationProvider>
        <Sidebar />

        {/* Content Viewport */}
        <div className="pl-64 relative z-10 min-h-screen flex flex-col">
          <Header />
          <main className="w-full pt-16 flex-1 px-space-lg py-space-lg relative">
            {children}
          </main>
        </div>
        </LocationProvider>
      </body>
    </html>
  );
}
