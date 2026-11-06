import { QueryClient } from "@tanstack/react-query";
import {
  createRouter,
  parseSearchWith,
  stringifySearchWith,
} from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";

// Keep numeric IDs as plain query strings while retaining TanStack's JSON
// serialization for other search values. This also accepts older URLs whose
// IDs were JSON-encoded as quoted strings.
const parseSearch = parseSearchWith((value: string) =>
  /^\d+$/.test(value) ? value : JSON.parse(value),
);
const stringifySearch = stringifySearchWith(JSON.stringify);

export const getRouter = () => {
  const queryClient = new QueryClient();

  const router = createRouter({
    routeTree,
    context: { queryClient },
    parseSearch,
    stringifySearch,
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
  });

  return router;
};
