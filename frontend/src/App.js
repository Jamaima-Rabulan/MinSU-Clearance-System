import { useEffect } from "react";

function App() {
  useEffect(() => {
    // Inject MinSU vanilla stylesheet + fonts once
    if (!document.getElementById("minsu-style")) {
      const link = document.createElement("link");
      link.id = "minsu-style";
      link.rel = "stylesheet";
      link.href = "/css/style.css";
      document.head.appendChild(link);
    }

    // Expose backend URL to vanilla JS
    window.__MINSU_BACKEND_URL__ = process.env.REACT_APP_BACKEND_URL || "";

    // Load the vanilla app only once
    if (!document.getElementById("minsu-app-script")) {
      const s = document.createElement("script");
      s.id = "minsu-app-script";
      s.src = "/js/app.js";
      s.async = false;
      document.body.appendChild(s);
    }

    return () => {
      // Do not tear down — the vanilla app owns #app container
    };
  }, []);

  return <div id="app" data-testid="minsu-app-root" />;
}

export default App;
