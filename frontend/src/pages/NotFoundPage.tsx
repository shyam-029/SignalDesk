import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";

export default function NotFoundPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-28 text-center md:px-6">
      <p className="num text-sm text-faint">404</p>
      <h1 className="mt-3 font-display text-3xl font-semibold">
        This page doesn't exist in the catalog.
      </h1>
      <p className="mx-auto mt-3 max-w-md text-sm text-muted">
        The research universe covers the Nifty 50. Try the markets list to find a company.
      </p>
      <Button asChild className="mt-7">
        <Link to="/markets">Browse markets</Link>
      </Button>
    </div>
  );
}
