#include <stdio.h>
void main(){
	int k,e,m;
	double even;
	printf("[국어, 영어, 수학]순으로 점수를 입력하시오: ");
	scanf("%d %d %d",&k,&e,&m);
	even = (k+e+m)/3;
	if(even>=90)
	{
	printf("축하합니다.장학금 대상자입니다.\n");
	printf("당신의 평균점수는 %lf입니다.",even);}
	else
	printf("당신의 평균점수는 %lf입니다.",even); 
}
