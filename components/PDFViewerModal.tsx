import { PDFViewer } from "./media/PDFViewer";

export default function PDFViewerModal(props: {
  lectureId: string;
  title: string;
  isOpen: boolean;
  onClose: () => void;
}) {
  return (
    <PDFViewer
      lectureId={props.lectureId}
      title={props.title}
      isOpen={props.isOpen}
      onClose={props.onClose}
    />
  );
}

export { PDFViewer };
