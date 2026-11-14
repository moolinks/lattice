import { Link } from "react-router-dom";
import { ArrowLeft, Compass } from "lucide-react";

export function NotFound() {
  return (
    <div className="page not-found">
      <Compass size={40} strokeWidth={1.2} />
      <span className="eyebrow">404 / OFF THE MAP</span>
      <h1>这个坐标不存在</h1>
      <p>页面可能被移动，或者链接指向了尚未创建的实体。</p>
      <Link to="/" className="btn btn-primary"><ArrowLeft size={14} /> 回到今日</Link>
    </div>
  );
}
