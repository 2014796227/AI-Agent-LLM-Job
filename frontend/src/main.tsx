// 不导入 React：jsx=react-jsx 变换自动注入运行时，显式导入在
// noUnusedLocals 下为未使用变量（v18 内容钉死，与 tsconfig 对齐）
import { createRoot } from "react-dom/client";
import App from "./App";

createRoot(document.getElementById("root")!).render(<App />);
