; ModuleID = 'kernel_map.bc'
source_filename = "fmcw_mapping.c"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"

; Function Attrs: nofree norecurse nounwind uwtable
define dso_local void @fmcw_window_map(float* nocapture readonly %0, float* nocapture readonly %1, float* nocapture readonly %2, float* nocapture %3, float* nocapture %4) local_unnamed_addr #0 {
  br label %7

6:                                                ; preds = %7
  ret void

7:                                                ; preds = %5, %7
  %8 = phi i64 [ 0, %5 ], [ %20, %7 ]
  %9 = getelementptr inbounds float, float* %0, i64 %8
  %10 = load float, float* %9, align 4, !tbaa !2
  %11 = getelementptr inbounds float, float* %2, i64 %8
  %12 = load float, float* %11, align 4, !tbaa !2
  %13 = fmul float %10, %12
  %14 = getelementptr inbounds float, float* %3, i64 %8
  store float %13, float* %14, align 4, !tbaa !2
  %15 = getelementptr inbounds float, float* %1, i64 %8
  %16 = load float, float* %15, align 4, !tbaa !2
  %17 = load float, float* %11, align 4, !tbaa !2
  %18 = fmul float %16, %17
  %19 = getelementptr inbounds float, float* %4, i64 %8
  store float %18, float* %19, align 4, !tbaa !2
  %20 = add nuw nsw i64 %8, 1
  %21 = icmp eq i64 %20, 256
  br i1 %21, label %6, label %7, !llvm.loop !6
}

; Function Attrs: nofree norecurse nounwind uwtable
define dso_local void @fmcw_fft_stage_map(float* nocapture %0, float* nocapture %1, float* nocapture readonly %2, float* nocapture readonly %3) local_unnamed_addr #0 {
  br label %6

5:                                                ; preds = %6
  ret void

6:                                                ; preds = %4, %6
  %7 = phi i64 [ 0, %4 ], [ %31, %6 ]
  %8 = add nuw nsw i64 %7, 128
  %9 = getelementptr inbounds float, float* %0, i64 %8
  %10 = load float, float* %9, align 4, !tbaa !2
  %11 = getelementptr inbounds float, float* %1, i64 %8
  %12 = load float, float* %11, align 4, !tbaa !2
  %13 = getelementptr inbounds float, float* %2, i64 %7
  %14 = load float, float* %13, align 4, !tbaa !2
  %15 = fmul float %10, %14
  %16 = getelementptr inbounds float, float* %3, i64 %7
  %17 = load float, float* %16, align 4, !tbaa !2
  %18 = fmul float %12, %17
  %19 = fsub float %15, %18
  %20 = fmul float %12, %14
  %21 = fmul float %10, %17
  %22 = fadd float %20, %21
  %23 = getelementptr inbounds float, float* %0, i64 %7
  %24 = load float, float* %23, align 4, !tbaa !2
  %25 = getelementptr inbounds float, float* %1, i64 %7
  %26 = load float, float* %25, align 4, !tbaa !2
  %27 = fadd float %24, %19
  store float %27, float* %23, align 4, !tbaa !2
  %28 = fadd float %26, %22
  store float %28, float* %25, align 4, !tbaa !2
  %29 = fsub float %24, %19
  store float %29, float* %9, align 4, !tbaa !2
  %30 = fsub float %26, %22
  store float %30, float* %11, align 4, !tbaa !2
  %31 = add nuw nsw i64 %7, 1
  %32 = icmp eq i64 %31, 128
  br i1 %32, label %5, label %6, !llvm.loop !9
}

; Function Attrs: nofree norecurse nounwind uwtable
define dso_local void @fmcw_transpose_map(float* nocapture readonly %0, float* nocapture %1, i32 %2) local_unnamed_addr #0 {
  %4 = shl nsw i32 %2, 8
  %5 = sext i32 %4 to i64
  %6 = sext i32 %2 to i64
  br label %8

7:                                                ; preds = %8
  ret void

8:                                                ; preds = %3, %8
  %9 = phi i64 [ 0, %3 ], [ %16, %8 ]
  %10 = add nuw nsw i64 %9, %5
  %11 = getelementptr inbounds float, float* %0, i64 %10
  %12 = load float, float* %11, align 4, !tbaa !2
  %13 = shl nuw nsw i64 %9, 7
  %14 = add nsw i64 %13, %6
  %15 = getelementptr inbounds float, float* %1, i64 %14
  store float %12, float* %15, align 4, !tbaa !2
  %16 = add nuw nsw i64 %9, 1
  %17 = icmp eq i64 %16, 256
  br i1 %17, label %7, label %8, !llvm.loop !10
}

; Function Attrs: nofree nounwind uwtable
define dso_local void @fmcw_accumulate_power_map(float* nocapture readonly %0, float* nocapture readonly %1, float* nocapture %2, i32 %3, i32 %4) local_unnamed_addr #1 {
  %6 = sext i32 %3 to i64
  %7 = sext i32 %4 to i64
  br label %10

8:                                                ; preds = %10
  %9 = getelementptr inbounds float, float* %2, i64 %7
  store float %22, float* %9, align 4, !tbaa !2
  ret void

10:                                               ; preds = %5, %10
  %11 = phi i64 [ 0, %5 ], [ %23, %10 ]
  %12 = phi float [ 0.000000e+00, %5 ], [ %22, %10 ]
  %13 = mul nsw i64 %11, %6
  %14 = add nsw i64 %13, %7
  %15 = getelementptr inbounds float, float* %0, i64 %14
  %16 = load float, float* %15, align 4, !tbaa !2
  %17 = getelementptr inbounds float, float* %1, i64 %14
  %18 = load float, float* %17, align 4, !tbaa !2
  %19 = fmul float %16, %16
  %20 = fmul float %18, %18
  %21 = fadd float %19, %20
  %22 = fadd float %12, %21
  %23 = add nuw nsw i64 %11, 1
  %24 = icmp eq i64 %23, 4
  br i1 %24, label %8, label %10, !llvm.loop !11
}

; Function Attrs: nofree norecurse nounwind uwtable
define dso_local void @fmcw_cfar_2d_map(float* nocapture readonly %0, float* nocapture %1, i32* nocapture %2, i32 %3, i32 %4, i32 %5) local_unnamed_addr #0 {
  %7 = add i32 %5, 1
  %8 = icmp ult i32 %7, 3
  %9 = mul nsw i32 %5, %4
  %10 = add i32 %3, -5
  %11 = add i32 %10, %9
  br i1 %8, label %15, label %12

12:                                               ; preds = %6
  %13 = load float, float* %1, align 4, !tbaa !2
  %14 = load i32, i32* %2, align 4, !tbaa !12
  br label %35

15:                                               ; preds = %6, %30
  %16 = phi i64 [ %31, %30 ], [ 0, %6 ]
  %17 = trunc i64 %16 to i32
  %18 = add i32 %17, -4
  %19 = icmp ult i32 %18, 3
  br i1 %19, label %30, label %20

20:                                               ; preds = %15
  %21 = trunc i64 %16 to i32
  %22 = add i32 %11, %21
  %23 = sext i32 %22 to i64
  %24 = getelementptr inbounds float, float* %0, i64 %23
  %25 = load float, float* %24, align 4, !tbaa !2
  %26 = load float, float* %1, align 4, !tbaa !2
  %27 = fadd float %25, %26
  store float %27, float* %1, align 4, !tbaa !2
  %28 = load i32, i32* %2, align 4, !tbaa !12
  %29 = add nsw i32 %28, 1
  store i32 %29, i32* %2, align 4, !tbaa !12
  br label %30

30:                                               ; preds = %20, %15
  %31 = add nuw nsw i64 %16, 1
  %32 = icmp eq i64 %31, 11
  br i1 %32, label %34, label %15, !llvm.loop !14

33:                                               ; preds = %35
  store i32 %45, i32* %2, align 4, !tbaa !12
  br label %34

34:                                               ; preds = %30, %33
  ret void

35:                                               ; preds = %12, %35
  %36 = phi i32 [ %14, %12 ], [ %45, %35 ]
  %37 = phi float [ %13, %12 ], [ %44, %35 ]
  %38 = phi i64 [ 0, %12 ], [ %46, %35 ]
  %39 = trunc i64 %38 to i32
  %40 = add i32 %11, %39
  %41 = sext i32 %40 to i64
  %42 = getelementptr inbounds float, float* %0, i64 %41
  %43 = load float, float* %42, align 4, !tbaa !2
  %44 = fadd float %43, %37
  store float %44, float* %1, align 4, !tbaa !2
  %45 = add nsw i32 %36, 1
  %46 = add nuw nsw i64 %38, 1
  %47 = icmp eq i64 %46, 11
  br i1 %47, label %33, label %35, !llvm.loop !14
}

attributes #0 = { nofree norecurse nounwind uwtable "disable-tail-calls"="false" "frame-pointer"="none" "less-precise-fpmad"="false" "min-legal-vector-width"="0" "no-infs-fp-math"="false" "no-jump-tables"="false" "no-nans-fp-math"="false" "no-signed-zeros-fp-math"="false" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" "unsafe-fp-math"="false" "use-soft-float"="false" }
attributes #1 = { nofree nounwind uwtable "disable-tail-calls"="false" "frame-pointer"="none" "less-precise-fpmad"="false" "min-legal-vector-width"="0" "no-infs-fp-math"="false" "no-jump-tables"="false" "no-nans-fp-math"="false" "no-signed-zeros-fp-math"="false" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" "unsafe-fp-math"="false" "use-soft-float"="false" }

!llvm.module.flags = !{!0}
!llvm.ident = !{!1}

!0 = !{i32 1, !"wchar_size", i32 4}
!1 = !{!"Ubuntu clang version 12.0.1-19ubuntu3"}
!2 = !{!3, !3, i64 0}
!3 = !{!"float", !4, i64 0}
!4 = !{!"omnipotent char", !5, i64 0}
!5 = !{!"Simple C/C++ TBAA"}
!6 = distinct !{!6, !7, !8}
!7 = !{!"llvm.loop.mustprogress"}
!8 = !{!"llvm.loop.unroll.disable"}
!9 = distinct !{!9, !7, !8}
!10 = distinct !{!10, !7, !8}
!11 = distinct !{!11, !7, !8}
!12 = !{!13, !13, i64 0}
!13 = !{!"int", !4, i64 0}
!14 = distinct !{!14, !7, !8}
