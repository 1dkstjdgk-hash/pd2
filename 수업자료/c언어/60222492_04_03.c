#include <stdio.h>
void main(){
	double cel,fah;
	
	printf("화씨 온도를 입력하시오:");
	scanf("%lf",&fah);
	cel = (5/9.0)*(fah - 32) ;
	printf("섭씨온도는 %lf입니다.",cel); 
}
