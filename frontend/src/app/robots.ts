import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  if (process.env.GOATLAB_PUBLICATION_RIGHTS_APPROVED === "true") {
    return { rules: { userAgent: "*", allow: "/" } };
  }
  return { rules: { userAgent: "*", disallow: "/" } };
}
