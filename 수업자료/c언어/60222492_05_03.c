#include <stdio.h>
void main(){
	int fst,scd,thr,result;
	printf("정수 세개를 입력하시오:");
	scanf("%d %d %d",&fst,&scd,&thr);
	result = fst|(scd&thr);
	printf("연산결과는 %d다",result);
}
