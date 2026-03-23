#include <stdio.h>
void main(){
	double h,w,endr,ew;
	printf("당신의 키와 몸무게를 입력하시오:");
	scanf("%lf %lf",&h,&w);
	ew = (h - 100) * 0.9;
	endr = w - ew;
	printf("당신의 몸무게와 표준 몸무게의 차이:%lf",endr);
}
