#include <stdio.h>
void main(){
	double h,w,ew;
	printf("당신의 키와 몸무게를 입력하시오:");
	scanf("%lf %lf",&h,&w);
	ew = (h - 100) * 0.9;
	if(w>=ew-3&&w<=ew+3)
	 printf("표준 입니다.");
	else if(w<ew-3)
	 printf("저체중 입니다."); 
	else
	 printf("과체중 입니다.");

}
