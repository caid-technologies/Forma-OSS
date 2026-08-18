import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getLegalDocument, legalDocuments } from "../../../lib/legal-docs";
import LegalDocumentWorkspace from "../legal-document-workspace";

type LegalDocumentPageProps = {
  params: Promise<{
    slug: string;
  }>;
};

export function generateStaticParams() {
  return legalDocuments.map((document) => ({ slug: document.slug }));
}

export async function generateMetadata(props: LegalDocumentPageProps): Promise<Metadata> {
  const params = await props.params;
  const document = getLegalDocument(params.slug);
  if (!document) return {};
  return {
    title: `${document.title} | Forma`,
    description: document.summary,
  };
}

export default async function LegalDocumentPage(props: LegalDocumentPageProps) {
  const params = await props.params;
  const document = getLegalDocument(params.slug);
  if (!document) notFound();
  return <LegalDocumentWorkspace document={document} />;
}
